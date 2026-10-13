import asyncio

import pytest
from mcp import Client

from rapidoddsapi_mcp import defaults, formatting, server

PAID_TOOLS = {"get_odds", "get_futures", "get_results", "find_arbitrage", "find_value_bets"}

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

FUTURES = {
    "sport": "AFL",
    "season": 2027,
    "bookmakers": [
        {
            "name": "Sportsbet",
            "markets": [
                {
                    "key": "brownlow_medal_winner",
                    "outcomes": [
                        {"name": "Nick Daicos", "price": 3.75},
                        {"name": "Errol Gulden", "price": 9.0},
                    ],
                }
            ],
        },
        {
            "name": "TAB",
            "markets": [
                {
                    "key": "brownlow_medal_winner",
                    "outcomes": [
                        {"name": "Errol Gulden", "price": 9.0},
                        {"name": "Nick Daicos", "price": 3.5},
                    ],
                }
            ],
        },
    ],
}

NO_FUTURES = {"sport": "AFL", "season": 2027, "bookmakers": []}


class FakeClient:
    """Stands in for the SDK client, counting credits the way it does."""

    def __init__(self, odds=EMPTY, usage=USAGE_FREE, futures=NO_FUTURES):
        self.credits_used = 0
        self._odds = odds
        self._futures = futures
        self._usage = usage
        self.calls = []

    def get_odds(self, sport, market_types, bookmakers):
        self.calls.append((sport, tuple(market_types), tuple(bookmakers)))
        if self._odds.get("games"):
            self.credits_used += len(market_types) * -(-len(bookmakers) // 5)
        return self._odds

    def get_futures(self, sport, market_types, bookmakers, season=None):
        self.calls.append((sport, tuple(market_types), tuple(bookmakers), season))
        if self._futures.get("bookmakers"):
            self.credits_used += len(market_types) * -(-len(bookmakers) // 5)
        return self._futures

    def get_usage(self):
        return self._usage

    def get_sport(self, sport, markets=True):
        return {
            "id": sport,
            "name": sport,
            "markets": {
                "game": ["head_to_head_3_way", "draw_no_bet"],
                "team": [],
                "player_props": [],
            },
        }


@pytest.fixture
def fake(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(server, "get_client", lambda: client)
    return client


class TestDefaults:
    def test_nothing_named_means_every_feed(self):
        """Feeds price across regions, so any smaller default would leave out
        books that carry the game: Bet365 is the only NCAAF feed."""
        from rapidoddsapi import BOOKMAKERS

        assert defaults.resolve_bookmakers(None) == list(BOOKMAKERS)
        assert defaults.resolve_bookmakers([]) == list(BOOKMAKERS)

    def test_groups_expand(self):
        from rapidoddsapi import AU_BOOKMAKERS, EXCHANGES

        assert defaults.resolve_bookmakers(["AU"]) == list(AU_BOOKMAKERS)
        assert defaults.resolve_bookmakers(["exchanges"]) == list(EXCHANGES)

    def test_groups_mix_with_names_without_duplicates(self):
        """Bet365 is in both AU and US. Requested twice it would be paid for
        twice in the credit count."""
        books = defaults.resolve_bookmakers(["AU", "US", "Pinnacle", "Bet365"])

        assert len(books) == len(set(books))
        assert "Pinnacle" in books
        assert "DraftKings" in books

    def test_plain_names_pass_through(self):
        assert defaults.resolve_bookmakers(["Sportsbet", "TAB"]) == ["Sportsbet", "TAB"]

    def test_all_bookmakers_is_every_feed(self):
        """The API has no bookmaker endpoint and does not reject bad names, so
        without a list to hand the only way to find a feed is to guess and pay
        for each attempt."""
        from rapidoddsapi import BOOKMAKERS

        assert defaults.all_bookmakers() == BOOKMAKERS

    def test_devig_book_is_added_once(self):
        assert "Pinnacle" in defaults.with_devig_book(["Sportsbet"], "Pinnacle")
        already = ["Pinnacle", "Sportsbet"]
        assert defaults.with_devig_book(already, "Pinnacle") == already


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

    @staticmethod
    def one_book(market, outcomes):
        return {
            "sport": "NFL",
            "games": [
                {
                    "game": {
                        "commence_time": "2026-10-19T17:00:00",
                        "home_team": "Denver Broncos",
                        "away_team": "Seattle Seahawks",
                    },
                    "bookmakers": [
                        {"name": "DraftKings", "markets": [{"key": market, "outcomes": outcomes}]}
                    ],
                }
            ],
        }

    def test_a_players_over_and_under_stay_apart(self):
        """Grouped on player and line alone, Over and Under merged into one row
        and its best price could be the other side."""
        text = formatting.format_odds(
            self.one_book(
                "player_passing_yds",
                [
                    {"name": "Over", "price": 1.9, "point": 219.5, "player_name": "Sam Darnold"},
                    {"name": "Under", "price": 1.88, "point": 219.5, "player_name": "Sam Darnold"},
                ],
            ),
            ["DraftKings"],
        )
        assert "Sam Darnold Over 219.5" in text
        assert "Sam Darnold Under 219.5" in text

    def test_team_totals_stay_apart(self):
        text = formatting.format_odds(
            self.one_book(
                "alternate_team_total_points",
                [
                    {"name": "Over", "price": 1.83, "point": 20.5, "team_name": "Denver Broncos"},
                    {"name": "Over", "price": 1.95, "point": 20.5, "team_name": "Seattle Seahawks"},
                ],
            ),
            ["DraftKings"],
        )
        assert "Denver Broncos Over 20.5" in text
        assert "Seattle Seahawks Over 20.5" in text

    def test_winning_margin_bands_stay_apart(self):
        text = formatting.format_odds(
            self.one_book(
                "winning_margin",
                [
                    {"name": "Denver Broncos", "price": 3.3, "description": "Little Win 1-13"},
                    {"name": "Denver Broncos", "price": 6.5, "description": "Big Win 14+"},
                ],
            ),
            ["DraftKings"],
        )
        assert "Denver Broncos Little Win 1-13" in text
        assert "Denver Broncos Big Win 14+" in text


class TestFormatFutures:
    def test_favourites_first_with_best_price(self):
        text = formatting.format_futures(FUTURES, ["Sportsbet", "TAB"])

        assert "season 2027" in text
        lines = [line.strip() for line in text.splitlines()]
        daicos = next(i for i, line in enumerate(lines) if line.startswith("Nick Daicos"))
        gulden = next(i for i, line in enumerate(lines) if line.startswith("Errol Gulden"))
        assert daicos < gulden
        assert "3.75 (Sportsbet)" in lines[daicos]
        assert "TAB 3.5" in lines[daicos]

    def test_long_fields_are_cut(self):
        runners = [{"name": f"Player {i}", "price": 2.0 + i} for i in range(40)]
        response = {
            "sport": "AFL",
            "season": 2027,
            "bookmakers": [
                {"name": "TAB", "markets": [{"key": "brownlow_medal_winner", "outcomes": runners}]}
            ],
        }
        text = formatting.format_futures(response, ["TAB"])

        assert "Player 0 " in text
        assert "Player 39" not in text
        assert f"{40 - formatting.FUTURES_SHOWN} longer priced selections not shown" in text

    def test_empty_formats_to_nothing(self):
        assert formatting.format_futures(NO_FUTURES, ["TAB"]) == ""


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
    def test_defaults_to_every_feed(self, fake):
        from rapidoddsapi import BOOKMAKERS

        fake._odds = ONE_GAME

        text = server.get_odds("AFL")

        sport, markets, books = fake.calls[0]
        assert sport == "AFL"
        assert markets == ("head_to_head",)
        assert books == tuple(BOOKMAKERS)
        assert f"Cost: {-(-len(BOOKMAKERS) // 5)} credits." in text

    def test_a_group_narrows_the_request(self, fake):
        from rapidoddsapi import AU_BOOKMAKERS

        server.get_odds("AFL", bookmakers=["AU"])

        assert fake.calls[0][2] == tuple(AU_BOOKMAKERS)

    def test_empty_result_says_it_was_free(self, fake):
        text = server.get_odds("AFL")

        assert "No games for AFL" in text
        assert "Cost: 0 credits." in text
        assert "Nothing was charged" in text

    def test_empty_on_a_wrong_market_blames_the_market(self, fake):
        """Soccer has no head_to_head because of the draw. Left unexplained,
        the empty result reads as the season being over, which is a wrong
        conclusion a user would act on."""
        text = server.get_odds("EPL", market_types=["head_to_head"])

        assert "does not have 'head_to_head'" in text
        assert "do not read it as the season being over" in text

    def test_empty_on_a_valid_market_blames_the_fixtures(self, fake):
        text = server.get_odds("EPL", market_types=["draw_no_bet"])

        assert "market types are valid" in text
        assert "no fixtures priced right now" in text

    def test_unsupported_markets_only_flags_the_bad_ones(self, fake):
        wrong = server.unsupported_markets("EPL", ["draw_no_bet", "head_to_head"])

        assert wrong == ["head_to_head"]

    def test_explicit_bookmakers_are_respected(self, fake):
        server.get_odds("AFL", bookmakers=["Pinnacle"])

        assert fake.calls[0][2] == ("Pinnacle",)

    def test_cost_multiplies(self, fake):
        fake._odds = ONE_GAME

        text = server.get_odds(
            "AFL",
            market_types=["head_to_head", "alternate_lines"],
            bookmakers=["Sportsbet", "TAB", "Ladbrokes", "Bet365", "Pointsbet"],
        )

        # 2 markets x ceil(5 / 5) = 2
        assert "Cost: 2 credits." in text


class TestGetFutures:
    def test_costs_the_odds_formula(self, fake):
        fake._futures = FUTURES

        text = server.get_futures("AFL", ["brownlow_medal_winner"], bookmakers=["Sportsbet", "TAB"])

        sport, markets, books, season = fake.calls[0]
        assert (sport, markets, books, season) == (
            "AFL",
            ("brownlow_medal_winner",),
            ("Sportsbet", "TAB"),
            None,
        )
        assert "Nick Daicos" in text
        assert "Cost: 1 credit." in text

    def test_season_is_passed_through(self, fake):
        server.get_futures("AFL", ["premiership_winner"], season=2025)
        assert fake.calls[0][3] == 2025

    def test_a_match_key_is_called_out(self, fake):
        text = server.get_futures("AFL", ["head_to_head"])

        assert "'head_to_head' is not a futures key" in text
        assert "Cost: 0 credits." in text

    def test_a_valid_key_with_nothing_priced_blames_the_season(self, fake):
        text = server.get_futures("AFL", ["brownlow_3_votes"])

        assert "not priced right now" in text

    def test_list_sports_shows_futures_keys(self, fake):
        text = server.list_sports("AFL")

        assert "futures, for get_futures not get_odds" in text
        assert "  premiership_winner" in text

    def test_a_sport_without_futures_lists_none(self, fake):
        assert "futures" not in server.list_sports("NBA")


BANDED = {
    "sport": "AFLW",
    "games": [
        {
            "game": {
                "commence_time": "2026-10-17T02:05:00",
                "home_team": "Adelaide Crows (W)",
                "away_team": "Gold Coast SUNS (W)",
            },
            "bookmakers": [
                {
                    "name": book,
                    "markets": [
                        {
                            "key": "winning_margin_24",
                            "outcomes": [
                                {
                                    "name": "Adelaide Crows (W)",
                                    "price": 3.3,
                                    "description": "Little Win 1-24",
                                },
                                {
                                    "name": "Adelaide Crows (W)",
                                    "price": 12.5,
                                    "description": "Big Win 25+",
                                },
                                {
                                    "name": "Gold Coast SUNS (W)",
                                    "price": 2.15,
                                    "description": "Little Win 1-24",
                                },
                                {
                                    "name": "Gold Coast SUNS (W)",
                                    "price": 3.6,
                                    "description": "Big Win 25+",
                                },
                            ],
                        }
                    ],
                }
                for book in ("Sportsbet", "TAB")
            ],
        }
    ],
}


class TestBandedMarkets:
    def test_arbitrage_explains_rather_than_reporting_none(self, fake):
        """Read as "no arbitrage", a market that can never be paired looks like
        one that was checked and came up empty."""
        fake._odds = BANDED

        text = server.find_arbitrage("AFLW", market="winning_margin_24")

        assert "priced in bands" in text
        assert "No arbitrage" not in text

    def test_value_bets_explain_too(self, fake):
        fake._odds = BANDED

        assert "priced in bands" in server.find_value_bets("AFLW", market="winning_margin_24")


class TestValueBets:
    def test_a_named_book_is_always_requested(self, fake):
        """Without it there is nothing to de-vig, so the request would be paid
        for and return nothing."""
        server.find_value_bets("AFL", bookmakers=["Sportsbet", "TAB"], devig="Pinnacle")

        assert "Pinnacle" in fake.calls[0][2]

    def test_a_named_book_joins_a_group(self, fake):
        server.find_value_bets("AFL", bookmakers=["AU"], devig="Pinnacle")

        assert "Pinnacle" in fake.calls[0][2]

    def test_a_consensus_forces_no_particular_book(self, fake):
        """The default needs enough books, not any one of them, so nothing is
        seeded and the caller's list is requested as given."""
        server.find_value_bets("AFL", bookmakers=["Sportsbet", "TAB"])

        assert list(fake.calls[0][2]) == ["Sportsbet", "TAB"]

    def test_the_sdk_is_actually_called(self, fake):
        """Every tool turns an exception into text, so calling the SDK wrongly
        reads exactly like a failed request. This asserts the call went
        through, which is what an argument renamed in the SDK would break."""
        for devig in ("all", "Pinnacle"):
            assert not server.find_value_bets("AFL", devig=devig).startswith("Request failed")

    def test_an_empty_consensus_blames_the_book_count(self, fake):
        """Two books priced the game, and a consensus needs four. Left
        unexplained, a thin market reads as no value, which is a different
        conclusion."""
        fake._odds = ONE_GAME

        text = server.find_value_bets("AFL", market="head_to_head")

        assert "four bookmakers" in text
        assert "devig='Pinnacle'" in text

    def test_no_games_is_not_no_value(self, fake):
        """Nothing came back at all, so nothing was tested."""
        text = server.find_value_bets("AFL", market="draw_no_bet")

        assert "nothing to look at" in text
        assert "not the same as finding no opportunities" in text

    def test_no_games_on_a_wrong_market_blames_the_market(self, fake):
        text = server.find_arbitrage("AFL", market="head_to_head")

        assert "does not have 'head_to_head'" in text


class TestProtocol:
    """What the MCP client actually sees. No API key needed to inspect this."""

    @staticmethod
    def tools():
        async def listed():
            async with Client(server.server) as client:
                return (await client.list_tools()).tools

        return asyncio.run(listed())

    def test_exactly_six_tools(self):
        """Six clearly named tools, so the model picks the right one. Adding a
        seventh is a decision, not an accident."""
        assert {tool.name for tool in self.tools()} == PAID_TOOLS | {"list_sports"}

    def test_sport_is_required_on_every_paid_tool(self):
        """Nothing may run without an explicit sport, or a vague question could
        fan out across everything."""
        for tool in self.tools():
            if tool.name == "get_futures":
                assert tool.input_schema["required"] == ["sport", "market_types"]
            elif tool.name in PAID_TOOLS:
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
