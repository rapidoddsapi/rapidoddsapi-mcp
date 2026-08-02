import asyncio

import pytest
from mcp import Client

from rapidoddsapi_mcp import defaults, formatting, server

PAID_TOOLS = {"get_odds", "get_results", "find_arbitrage", "find_value_bets"}

KEY = "oa_your_api_key_here"

USAGE_FREE = {
    "tier": "free",
    "status": "active",
    "credits_used": 37,
    "credits_limit": 250,
    "credits_remaining": 213,
    "resets": False,
}

ONE_GAME = {
    "sport": "AFL",
    "games": [
        {
            "game": {
                "commence_time": "2026-08-02T03:10:58",
                "home_team": "Richmond",
                "away_team": "West Coast Eagles",
            },
            "bookmakers": [
                {
                    "name": "Sportsbet",
                    "markets": [
                        {
                            "key": "head_to_head",
                            "outcomes": [
                                {"name": "Richmond", "price": 2.13},
                                {"name": "West Coast Eagles", "price": 1.71},
                            ],
                        }
                    ],
                },
                {
                    "name": "TAB",
                    "markets": [
                        {
                            "key": "head_to_head",
                            "outcomes": [
                                {"name": "Richmond", "price": 2.30},
                                {"name": "West Coast Eagles", "price": 1.65},
                            ],
                        }
                    ],
                },
            ],
        }
    ],
}

EMPTY = {"sport": "AFL", "games": []}


class FakeClient:
    """Stands in for the SDK client, counting credits the way it does."""

    def __init__(self, odds=EMPTY, usage=USAGE_FREE):
        self.credits_used = 0
        self._odds = odds
        self._usage = usage
        self.calls = []

    def get_odds(self, sport, market_types, bookmakers):
        self.calls.append((sport, tuple(market_types), tuple(bookmakers)))
        if self._odds.get("games"):
            self.credits_used += len(market_types) * -(-len(bookmakers) // 5)
        return self._odds

    def get_usage(self):
        return self._usage


@pytest.fixture
def fake(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(server, "get_client", lambda: client)
    return client


class TestDefaults:
    def test_region_picks_local_books(self):
        assert defaults.default_bookmakers("AFL") == defaults.AU_DEFAULT
        assert defaults.default_bookmakers("NFL") == defaults.US_DEFAULT
        assert defaults.default_bookmakers("EPL") == defaults.EU_DEFAULT

    def test_unknown_sport_falls_back(self):
        assert defaults.default_bookmakers("QUIDDITCH") == defaults.EU_DEFAULT

    def test_default_is_one_credit_group(self):
        """Five books is ceil(5/5) = 1, the cheapest useful request."""
        for sport in ("AFL", "NFL", "EPL"):
            assert len(defaults.default_bookmakers(sport)) == 5

    def test_wide_is_wider_and_unique(self):
        books = defaults.wide_bookmakers("AFL")
        assert len(books) == defaults.ARBITRAGE_DEFAULT_COUNT
        assert len(set(books)) == len(books)

    def test_wide_starts_from_the_region(self):
        assert list(defaults.wide_bookmakers("AFL"))[:5] == list(defaults.AU_DEFAULT)

    def test_region_bookmakers_is_the_full_regional_list(self):
        """The API has no bookmaker endpoint and does not reject bad names, so
        without a list to hand the only way to find a feed is to guess and pay
        for each attempt."""
        from rapidoddsapi import AU_BOOKMAKERS, BOOKMAKERS, US_BOOKMAKERS

        assert defaults.region_bookmakers("AFL") == AU_BOOKMAKERS
        assert defaults.region_bookmakers("NFL") == US_BOOKMAKERS
        # Soccer and tennis are priced in every region, not just Europe.
        assert defaults.region_bookmakers("EPL") == BOOKMAKERS

    def test_region_list_is_a_superset_of_the_default(self):
        for sport in ("AFL", "NFL", "EPL"):
            region = set(defaults.region_bookmakers(sport))
            assert set(defaults.default_bookmakers(sport)) <= region

    def test_with_sharp_adds_it_once(self):
        assert defaults.SHARP_BOOKMAKER in defaults.with_sharp(["Sportsbet"])
        already = ["Pinnacle", "Sportsbet"]
        assert list(defaults.with_sharp(already)) == already


class TestCreditLine:
    def test_reports_cost_and_balance(self):
        line = formatting.credit_line(2, USAGE_FREE)
        assert "Cost: 2 credits." in line
        assert "213 of 250 remaining" in line

    def test_free_tier_says_it_does_not_reset(self):
        assert "do not reset" in formatting.credit_line(1, USAGE_FREE)

    def test_paid_tier_does_not(self):
        paid = {**USAGE_FREE, "tier": "pro", "resets": True}
        assert "do not reset" not in formatting.credit_line(1, paid)

    def test_singular_credit(self):
        assert "Cost: 1 credit." in formatting.credit_line(1, USAGE_FREE)

    def test_zero_does_not_claim_the_call_was_empty(self):
        """list_sports costs nothing but does return data, so the footer must
        not imply the opposite."""
        assert formatting.credit_line(0, USAGE_FREE).startswith("Cost: 0 credits.")

    def test_survives_a_missing_balance(self):
        assert formatting.credit_line(1, None) == "Cost: 1 credit."


SPLIT_ACROSS_BOOKS = {
    "sport": "AFL",
    "games": [
        {
            "game": {
                "commence_time": "2026-08-02T03:10:58",
                "home_team": "Richmond",
                "away_team": "West Coast Eagles",
            },
            "bookmakers": [ONE_GAME["games"][0]["bookmakers"][0]],
        },
        {
            # Same fixture, but Bet365 lists it an hour later. This is real
            # behaviour, and it must still merge into one game.
            "game": {
                "commence_time": "2026-08-02T04:10:00",
                "home_team": "Richmond",
                "away_team": "West Coast Eagles",
            },
            "bookmakers": [ONE_GAME["games"][0]["bookmakers"][1]],
        },
    ],
}


class TestFormatOdds:
    def test_best_price_leads_each_selection(self):
        text = formatting.format_odds(ONE_GAME, ["Sportsbet", "TAB"])
        richmond = next(line for line in text.splitlines() if "Richmond" in line and "2.3" in line)
        assert "2.3 (TAB)" in richmond
        assert "Sportsbet 2.13" in richmond

    def test_one_entry_per_bookmaker_merges_into_one_game(self):
        """The API returns a fixture once per book. Without merging, every
        game shows a single price and line shopping is impossible."""
        text = formatting.format_odds(SPLIT_ACROSS_BOOKS, ["Sportsbet", "TAB"])

        assert "1 game(s)" in text
        assert text.count("head_to_head") == 1
        richmond = next(line for line in text.splitlines() if line.strip().startswith("Richmond"))
        assert "2.3 (TAB)" in richmond
        assert "Sportsbet 2.13" in richmond

    def test_empty_response_formats_to_nothing(self):
        assert formatting.format_odds(EMPTY, ["Sportsbet"]) == ""


AFL_SCORE = {
    "home": {"team": "Adelaide Crows", "goals": 11, "behinds": 8, "points": 74},
    "away": {"team": "Collingwood", "goals": 16, "behinds": 12, "points": 108},
    "totals": {
        "full_time": {"goals": 27, "behinds": 20, "points": 182},
        "half_time": None,
        "by_period": [{"period": 1, "points": 53}],
    },
    "period_state": [{"period": 1, "completed": True}, {"period": 2, "completed": False}],
}

MLB_SCORE = {
    "home": {"team": "Tampa Bay Rays", "runs": 1, "hits": 6, "errors": 0},
    "away": {"team": "Cleveland Guardians", "runs": 0, "hits": 1, "errors": 0},
    "totals": {"full_time": {"runs": 1, "hits": 7}, "first_5_innings": {"runs": 1}},
}


class TestFormatResults:
    """Scoring fields differ by sport, so nothing here may assume 'points'."""

    def test_afl_keeps_its_own_fields(self):
        text = "\n".join(formatting._score_lines(AFL_SCORE))

        assert "Adelaide Crows: goals 11, behinds 8, points 74" in text
        assert "full_time (both teams): goals 27, behinds 20, points 182" in text
        assert "periods: 1 of 2 complete" in text

    def test_mlb_keeps_its_own_fields(self):
        text = "\n".join(formatting._score_lines(MLB_SCORE))

        assert "Tampa Bay Rays: runs 1, hits 6, errors 0" in text
        assert "first_5_innings (both teams): runs 1" in text
        assert "points" not in text

    def test_null_named_total_is_skipped(self):
        """half_time is null until the half is over, and must not print."""
        assert "half_time" not in "\n".join(formatting._score_lines(AFL_SCORE))

    def test_score_without_period_state_does_not_crash(self):
        assert formatting._score_lines(MLB_SCORE)

    def test_upcoming_game_has_no_score_block(self):
        response = {"sport": "AFL", "games": [{"game": {"home_team": "a", "away_team": "b"}}]}
        assert "1 game(s)" in formatting.format_results(response)


class TestGetOdds:
    def test_defaults_cost_one_credit(self, fake):
        fake._odds = ONE_GAME

        text = server.get_odds("AFL")

        sport, markets, books = fake.calls[0]
        assert sport == "AFL"
        assert markets == ("head_to_head",)
        assert books == defaults.AU_DEFAULT
        assert "Cost: 1 credit." in text

    def test_empty_result_says_it_was_free(self, fake):
        text = server.get_odds("AFL")

        assert "No games for AFL" in text
        assert "Cost: 0 credits." in text
        assert "Nothing was charged" in text

    def test_explicit_bookmakers_are_respected(self, fake):
        server.get_odds("AFL", bookmakers=["Pinnacle"])

        assert fake.calls[0][2] == ("Pinnacle",)

    def test_cost_multiplies(self, fake):
        fake._odds = ONE_GAME

        text = server.get_odds("AFL", market_types=["head_to_head", "alternate_lines"])

        # 2 markets x ceil(5 / 5) = 2
        assert "Cost: 2 credits." in text


class TestValueBets:
    def test_sharp_book_is_always_requested(self, fake):
        server.find_value_bets("AFL", bookmakers=["Sportsbet", "TAB"])

        assert defaults.SHARP_BOOKMAKER in fake.calls[0][2]

    def test_sharp_does_not_push_the_default_over_a_credit_group(self, fake):
        """Appending the sharp book to ten would make eleven, and
        ceil(11 / 5) is 3 credits where the description promises 2."""
        server.find_value_bets("AFL")

        books = fake.calls[0][2]
        assert defaults.SHARP_BOOKMAKER in books
        assert len(books) == defaults.ARBITRAGE_DEFAULT_COUNT
        assert -(-len(books) // 5) == 2


class TestProtocol:
    """What the MCP client actually sees. No API key needed to inspect this."""

    @staticmethod
    def tools():
        async def listed():
            async with Client(server.server) as client:
                return (await client.list_tools()).tools

        return asyncio.run(listed())

    def test_exactly_five_tools(self):
        """Five clearly named tools, so the model picks the right one. Adding a
        sixth is a decision, not an accident."""
        assert {tool.name for tool in self.tools()} == PAID_TOOLS | {"list_sports"}

    def test_sport_is_required_on_every_paid_tool(self):
        """Nothing may run without an explicit sport, or a vague question could
        fan out across everything."""
        for tool in self.tools():
            if tool.name in PAID_TOOLS:
                assert tool.input_schema["required"] == ["sport"]

    def test_only_list_sports_needs_nothing(self):
        free = next(t for t in self.tools() if t.name == "list_sports")
        assert free.input_schema.get("required", []) == []

    def test_descriptions_state_the_cost(self):
        """The description is what the model reads before spending, so the
        price has to be in it."""
        for tool in self.tools():
            assert "credit" in (tool.description or "").lower()


class TestErrors:
    def test_missing_key_is_explained(self, monkeypatch):
        monkeypatch.delenv(server.API_KEY_ENV, raising=False)
        monkeypatch.setattr(server, "_client", None)

        text = server.list_sports()

        assert server.API_KEY_ENV in text
        assert "oa_" in text

    def test_out_of_credits_tells_the_model_to_stop(self):
        from rapidoddsapi.exceptions import InsufficientCreditsError

        text = server._explain(InsufficientCreditsError("Insufficient credits.", 429, 3))

        assert "3 credits remain" in text
        assert "Stop making paid requests" in text
