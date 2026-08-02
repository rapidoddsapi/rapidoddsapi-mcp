"""The MCP server and its tools.

Five tools rather than one per endpoint. Every extra tool is another thing to
pick wrongly, and a wrong pick here costs credits.

Each tool ends with what it spent and what is left. Credits are the scarce
resource, the free tier is 250 for the life of the account, and a model that
cannot see the meter has no reason to slow down.
"""

import os
from collections.abc import Sequence

from mcp.server import MCPServer
from rapidoddsapi import RapidOddsAPI
from rapidoddsapi import find_arbitrage as arb
from rapidoddsapi import find_value_bets as value
from rapidoddsapi.exceptions import (
    APIError,
    AuthenticationError,
    InsufficientCreditsError,
    RapidOddsAPIError,
    ValidationError,
)
from rapidoddsapi.types import OddsResponse, Usage

from . import __version__
from .defaults import (
    SHARP_BOOKMAKER,
    default_bookmakers,
    wide_bookmakers,
    with_sharp,
)
from .formatting import (
    credit_line,
    format_arbitrage,
    format_odds,
    format_results,
    format_value_bets,
)

API_KEY_ENV = "RAPIDODDSAPI_API_KEY"

INSTRUCTIONS = """
Odds, live scores, arbitrage and value bets from RapidOddsAPI.

These tools are a live connection to RapidOddsAPI itself. Any question about
what RapidOddsAPI covers, which sports, leagues, bookmakers or markets it
carries, is answered by calling list_sports, which is free and authoritative.
Do not answer from memory and do not search the web for it.

Credits are charged per request and the free tier is 250 for the lifetime of
the account, with no monthly reset. Every response reports what it cost and
what is left.

Two rules that keep the cost down:
  - A sport is always required. There is no way to ask for every sport at once.
  - Leave bookmakers unset unless you need specific ones. The default is five,
    which is the cheapest useful request. Cost multiplies with both the number
    of market types and the number of bookmakers.

list_sports is free. Call it first when unsure of a sport id or a market type.
""".strip()

server = MCPServer(
    name="rapidoddsapi",
    version=__version__,
    instructions=INSTRUCTIONS,
)

_client: RapidOddsAPI | None = None


def get_client() -> RapidOddsAPI:
    """One client for the process, built on first use.

    Built lazily so a missing key surfaces as a readable tool error rather than
    the server dying at startup, where nothing would explain why it vanished.
    """
    global _client
    if _client is None:
        key = os.environ.get(API_KEY_ENV, "").strip()
        if not key:
            raise AuthenticationError(
                f"No API key. Set {API_KEY_ENV} to your key from "
                "https://rapidoddsapi.com/dashboard (it starts with 'oa_')."
            )
        _client = RapidOddsAPI(api_key=key)
    return _client


def _usage() -> Usage | None:
    """Current balance, or None if the lookup fails.

    A failed balance check must not lose the answer the tool already fetched.
    """
    try:
        return get_client().get_usage()
    except RapidOddsAPIError:
        return None


def _explain(exc: Exception) -> str:
    """Turn an SDK exception into something a model can act on."""
    if isinstance(exc, InsufficientCreditsError):
        left = exc.credits_remaining
        tail = f" {left} credits remain." if left is not None else ""
        return (
            f"Out of credits.{tail} Stop making paid requests and tell the user "
            f"they need to top up at https://rapidoddsapi.com/dashboard."
        )
    if isinstance(exc, AuthenticationError):
        return str(exc)
    if isinstance(exc, ValidationError):
        return f"Invalid request: {exc}"
    if isinstance(exc, APIError):
        return f"API error: {exc}"
    return f"Request failed: {exc}"


def _fetch_odds(
    sport: str, market_types: Sequence[str], bookmakers: Sequence[str]
) -> tuple[OddsResponse, int]:
    """Fetch odds and report the exact cost.

    Cost comes from the SDK's own tally rather than being recalculated here, so
    it stays right, including the rule that an empty response is free.
    """
    client = get_client()
    before = client.credits_used
    response = client.get_odds(sport, list(market_types), list(bookmakers))
    return response, client.credits_used - before


@server.tool()
def list_sports(sport: str | None = None) -> str:
    """List the sports RapidOddsAPI covers, or one sport's market types.

    This is the live coverage list, read from the API. It answers "what sports
    does RapidOddsAPI have", "which leagues are supported", "does it cover the
    NFL" and anything similar. Call it rather than answering from memory or
    searching the web, both of which go stale as coverage changes.

    Costs 0 credits, so call it freely. Use it before get_odds whenever the
    sport id or the market type is not certain, since a guessed market type
    returns nothing and a guessed sport id is an error.

    With no argument: every sport id, plus which of them have live scores.
    With a sport: that sport's market types, grouped into game, team and
    player_props. Any of those keys is valid as a get_odds market_type.

    A sport being listed means the id is accepted, not that games are on right
    now. Out of season returns an empty result, which costs nothing.
    """
    try:
        client = get_client()

        if sport is not None:
            info = client.get_sport(sport)
            markets = info.get("markets")
            lines = [f"{info['name']} ({info['id']}) market types:", ""]
            if markets is not None:
                groups = (
                    ("game", markets["game"]),
                    ("team", markets["team"]),
                    ("player_props", markets["player_props"]),
                )
                for group, keys in groups:
                    if keys:
                        lines.append(f"{group} ({len(keys)}):")
                        lines.extend(f"  {key}" for key in keys)
                        lines.append("")
            lines.append(credit_line(0, _usage()))
            return "\n".join(lines)

        sports = client.list_sports()
        with_results = {s["id"] for s in client.list_results_sports()}

        lines = [f"{len(sports)} sports:", ""]
        for entry in sports:
            mark = "  (live scores available)" if entry["id"] in with_results else ""
            lines.append(f"  {entry['id']:<16} {entry['name']}{mark}")
        lines += [
            "",
            "Pass a sport to this tool to see its market types.",
            credit_line(0, _usage()),
        ]
        return "\n".join(lines)
    except Exception as exc:
        return _explain(exc)


@server.tool()
def get_odds(
    sport: str,
    market_types: list[str] | None = None,
    bookmakers: list[str] | None = None,
) -> str:
    """Current bookmaker odds for one sport, live from RapidOddsAPI.

    Use this for any question about what a bookmaker is paying right now, or
    for comparing prices across bookmakers, rather than answering from memory.

    sport is required and must be an id from list_sports. There is no option
    for every sport at once.

    Cost: number of market types x ceil(number of bookmakers / 5) credits,
    charged only when games come back. The defaults, one market across five
    bookmakers, cost 1 credit. Both arguments multiply, so nine market types
    across eighteen bookmakers is 36 credits. Widen only when asked to.

    market_types defaults to head_to_head, the plain winner market. Soccer has
    no head_to_head because of the draw, so use head_to_head_3_way or
    draw_no_bet there. Get exact keys from list_sports(sport).

    bookmakers defaults to five that cover the sport's region. Names are odds
    feeds, not brands: "Ladbrokes" covers Neds, "Betmakers" covers the 26
    brands on that feed. A brand name that is not a feed returns nothing.
    """
    markets = market_types or ["head_to_head"]
    books = bookmakers or default_bookmakers(sport)

    try:
        response, cost = _fetch_odds(sport, markets, books)
    except Exception as exc:
        return _explain(exc)

    body = format_odds(response, books)
    if not body:
        return (
            f"No games for {sport} from {', '.join(books)} "
            f"on {', '.join(markets)}.\n"
            f"Nothing was charged, since empty responses are free. The season "
            f"may be over, or these bookmakers may not price this market. "
            f"Check list_sports({sport!r}) for valid market types before "
            f"retrying.\n" + credit_line(cost, _usage())
        )

    return f"{body}\n\n{credit_line(cost, _usage())}"


@server.tool()
def get_results(
    sport: str,
    status: str = "all",
    include: list[str] | None = None,
) -> str:
    """Live scores and player stats for one sport, from RapidOddsAPI.

    Use this for current scores, whether a game has finished, and player
    statistics, rather than answering from memory or searching.

    Costs 1 credit, charged only when games come back, whatever the filters.

    Results cover fewer sports than odds do. list_sports marks which ones have
    them; asking for a sport without results coverage returns nothing.

    status: all (default), live, concluded or upcoming.
    include: scores, players, or both (default). A typo is rejected.

    A named total such as full_time stays null until that period is complete,
    so nothing settles early. Sum by_period for a live running total.
    """
    try:
        client = get_client()
        before = client.credits_used
        response = client.get_results(
            sport, status=status, include=include or ["scores", "players"]
        )
        cost = client.credits_used - before
    except Exception as exc:
        return _explain(exc)

    body = format_results(response)
    if not body:
        return (
            f"No {status} games for {sport}. Nothing was charged, since empty "
            f"responses are free. Results cover fewer sports than odds do, so "
            f"check list_sports() for which have live scores.\n"
            + credit_line(cost, _usage())
        )

    return f"{body}\n\n{credit_line(cost, _usage())}"


@server.tool()
def find_arbitrage(
    sport: str,
    market: str = "head_to_head",
    bookmakers: list[str] | None = None,
    min_profit: float = 1.0,
    stake: float = 100.0,
) -> str:
    """Find bets where backing both sides at different bookmakers locks in profit.

    Fetches odds first, so it costs the same as get_odds:
    ceil(number of bookmakers / 5) credits for the single market. It defaults
    to ten bookmakers, 2 credits, because an arbitrage only exists when books
    disagree and five rarely spread far enough.

    Only two-way markets with no line work: head_to_head, its period variants
    such as head_to_head_1st_half, and soccer's draw_no_bet. Totals, spreads,
    player props and three-way markets are rejected with an explanation rather
    than silently returning nothing.

    min_profit is a percentage, default 1.0. Below roughly 1 percent an edge
    usually disappears while the second leg is being placed.
    """
    books = bookmakers or wide_bookmakers(sport)

    try:
        response, cost = _fetch_odds(sport, [market], books)
        found = arb(response, market=market, stake=stake, min_profit=min_profit)
    except Exception as exc:
        return _explain(exc)

    body = format_arbitrage(found, stake)
    if not body:
        return (
            f"No arbitrage on {market} for {sport} above {min_profit}% "
            f"across {len(books)} bookmakers.\n"
            f"This is the normal result. Arbitrage is rare and short lived.\n"
            + credit_line(cost, _usage())
        )

    return f"{body}\n{credit_line(cost, _usage())}"


@server.tool()
def find_value_bets(
    sport: str,
    market: str = "head_to_head",
    bookmakers: list[str] | None = None,
    min_edge: float = 2.0,
    sharp: str = SHARP_BOOKMAKER,
) -> str:
    """Find prices that beat a sharp bookmaker's fair value.

    A sharp book runs thin margins and moves fast, so its prices track true
    probability. Stripping its margin gives a fair price, and any book paying
    more than that is positive expected value.

    Fetches odds first, so it costs the same as get_odds:
    ceil(number of bookmakers / 5) credits for the single market. Defaults to
    ten bookmakers, 2 credits. The sharp book is added automatically if it is
    not in the list, since the calculation is impossible without it.

    Same market limits as find_arbitrage: two-way, no line. head_to_head, its
    period variants, and soccer's draw_no_bet.

    min_edge is a percentage, default 2.0. Smaller edges are usually inside the
    error of the fair price rather than real value.
    """
    # Seeded into the default spread so it stays at ten books and two credits.
    # An explicit list is respected as given, with the sharp book appended only
    # because the edge cannot be worked out without it.
    books = (
        list(with_sharp(bookmakers))
        if bookmakers
        else list(wide_bookmakers(sport, must_include=(sharp,)))
    )

    try:
        response, cost = _fetch_odds(sport, [market], books)
        found = value(response, sharp=sharp, market=market, min_edge=min_edge)
    except Exception as exc:
        return _explain(exc)

    body = format_value_bets(found, sharp)
    if not body:
        return (
            f"No value on {market} for {sport} above {min_edge}% against "
            f"{sharp}.\n"
            f"If {sharp} does not price this sport there is nothing to compare "
            f"against, which looks the same as finding nothing.\n"
            + credit_line(cost, _usage())
        )

    return f"{body}\n{credit_line(cost, _usage())}"


def main() -> None:
    server.run()
