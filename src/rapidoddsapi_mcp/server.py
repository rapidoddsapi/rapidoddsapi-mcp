"""The MCP server and its tools.

Five tools rather than one per endpoint. Every extra tool is another thing to
pick wrongly, and a wrong pick here costs credits.

Each tool ends with what it spent and what is left. Credits are the scarce
resource, the free tier is 250 for the life of the account, and a model that
cannot see the meter has no reason to slow down.
"""

import os
from collections.abc import Sequence

import truststore
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
    all_bookmakers,
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

# Verify certificates against the operating system's trust store rather than
# the bundled one. Corporate networks and antivirus that inspect HTTPS present
# their own certificate, which the machine trusts and a bundled store does not,
# so without this the server installs cleanly and then fails every request with
# CERTIFICATE_VERIFY_FAILED. Must run before the first client is built.
truststore.inject_into_ssl()

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

Never guess a bookmaker or market name. An unknown one is not rejected, it
comes back with no prices, so trying names to see which work is both slow and
billable. list_sports(sport) returns every valid name for that sport and costs
nothing.

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


def unsupported_markets(sport: str, requested: Sequence[str]) -> list[str]:
    """Which of these market types the sport does not carry.

    Only worth asking once a response comes back empty. The API accepts any
    market string and returns nothing for one it does not recognise, so a
    misspelled or wrong-sport key is indistinguishable from a sport simply
    having no fixtures. Checking costs nothing.
    """
    try:
        markets = get_client().get_sport(sport).get("markets")
    except RapidOddsAPIError:
        return []
    if markets is None:
        return []

    valid = {*markets["game"], *markets["team"], *markets["player_props"]}
    return [key for key in requested if key not in valid]


def _no_games(sport: str, market: str) -> str:
    """Nothing came back at all, which is not the same as nothing being found.

    "No arbitrage" reads as having looked and found none, so a sport out of
    season or a market type this sport does not carry has to say so, or the
    model reports a conclusion it never tested.
    """
    wrong = unsupported_markets(sport, [market])
    if wrong:
        return (
            f"{sport} does not have '{market}', so there was nothing to look "
            f"at. Call list_sports({sport!r}) for the market types it carries "
            f"and retry with one of those."
        )
    return (
        f"No games priced for {sport} on {market}, so there was nothing to "
        f"look at. The season may be over or the fixtures not yet posted. "
        f"This is not the same as finding no opportunities."
    )


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
    player_props, and every bookmaker you can request for it. Any of those
    market keys is valid as a get_odds market_type, and any of those bookmaker
    names is valid as a get_odds bookmaker.

    Call this before naming bookmakers. Unrecognised names are not an error,
    they return no prices, so probing to find out which exist looks like a
    sport simply having no odds and costs credits for each attempt.

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
            feeds = all_bookmakers()
            lines.append(f"bookmakers you can request ({len(feeds)}):")
            lines.extend(f"  {feed}" for feed in feeds)
            lines += [
                "",
                "That is every feed, and they are not split by region: an "
                "American book pricing the AFL is normal. A name not on the "
                "list returns no prices, so do not try other bookmaker names "
                "to see what happens, each attempt can cost credits.",
                "These are feeds, not brands. One feed often carries several "
                "brands at identical prices, so the number of betting sites "
                "behind them is larger than the number of names here.",
                "Not every feed prices every sport or market.",
                "",
                credit_line(0, _usage()),
            ]
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

    bookmakers defaults to five that cover the sport's region. To use others,
    take the names from list_sports(sport), which lists every feed available.
    Never guess a name: an unknown one returns no prices rather than an error,
    so guessing is indistinguishable from the sport having no odds, and each
    guess can cost credits.

    Names are odds feeds, not brands. "Ladbrokes" is the feed that also carries
    Neds, "Betmakers" carries the 26 brands running on it, so a brand name that
    is not itself a feed returns nothing.
    """
    markets = market_types or ["head_to_head"]
    books = bookmakers or default_bookmakers(sport)

    try:
        response, cost = _fetch_odds(sport, markets, books)
    except Exception as exc:
        return _explain(exc)

    body = format_odds(response, books)
    if not body:
        lines = [
            f"No games for {sport} from {', '.join(books)} on "
            f"{', '.join(markets)}. Nothing was charged, since empty responses "
            f"are free."
        ]

        wrong = unsupported_markets(sport, markets)
        if wrong:
            lines.append(
                f"{sport} does not have {', '.join(repr(k) for k in wrong)}. "
                f"That is why the result is empty, and it would be empty "
                f"whatever the fixtures are, so do not read it as the season "
                f"being over. Call list_sports({sport!r}) for the market types "
                f"this sport actually carries and retry with one of those."
            )
        else:
            lines.append(
                f"The market types are valid for {sport}, so there are simply "
                f"no fixtures priced right now, whether out of season or not "
                f"yet posted. Retrying the same request will not change that."
            )

        lines.append(credit_line(cost, _usage()))
        return "\n".join(lines)

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

    Works on any market whose bets have two sides: head_to_head and its period
    variants, soccer's draw_no_bet, totals, handicaps, team totals and player
    props. Only three-way markets are rejected, with an explanation rather than
    silently returning nothing.

    On a market with a line each line is a separate bet, so a totals market can
    return several results for one game. Over 8.5 is never paired with Under
    9.5, and a handicap of -1.5 only ever with +1.5.

    min_profit is a percentage, default 1.0. Below roughly 1 percent an edge
    usually disappears while the second leg is being placed. Set it negative to
    see near misses.
    """
    books = bookmakers or wide_bookmakers(sport)

    try:
        response, cost = _fetch_odds(sport, [market], books)
        found = arb(response, market=market, stake=stake, min_profit=min_profit)
    except Exception as exc:
        return _explain(exc)

    body = format_arbitrage(found, stake)
    if not body:
        if not response.get("games"):
            return _no_games(sport, market) + "\n" + credit_line(cost, _usage())
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
    devig: str = "all",
) -> str:
    """Find prices that beat fair value.

    Bookmakers price in a margin, so their odds sum to more than certainty.
    Removing it leaves a fair price, and any book paying more than that is
    positive expected value.

    devig says where the fair price comes from, and is worth explaining to the
    user rather than just picking:

      "all"        the default. Every bookmaker fetched is de-vigged on its
                   own and the results averaged. Needs no view on which book
                   is sharp, works on markets Pinnacle does not price, and is
                   the one to use unless there is a reason not to.
      a book name  "Pinnacle" measures every other book against that one. A
                   sharp book runs thin margins and moves fast, so its prices
                   track true probability more closely than an average does.
                   Tighter, but only where that book prices the market, and it
                   cannot itself appear in the results.

    Fetches odds first, so it costs the same as get_odds:
    ceil(number of bookmakers / 5) credits for the single market. Defaults to
    ten bookmakers, 2 credits. Naming a book puts it in the request
    automatically, since the calculation is impossible without it.

    Same markets as find_arbitrage: head_to_head and its period variants,
    draw_no_bet, totals, handicaps, team totals and player props.

    min_edge is a percentage, default 2.0. Smaller edges are usually inside the
    error of the fair price rather than real value.
    """
    consensus = devig == "all"

    # The named book is seeded into the default spread rather than appended, so
    # it stays at ten books and two credits. A consensus needs no particular
    # book, only enough of them.
    if bookmakers:
        books = list(bookmakers) if consensus else list(with_sharp(bookmakers, devig))
    else:
        books = list(wide_bookmakers(sport, must_include=() if consensus else (devig,)))

    try:
        response, cost = _fetch_odds(sport, [market], books)
        found = value(response, devig=devig, market=market, min_edge=min_edge)
    except Exception as exc:
        return _explain(exc)

    body = format_value_bets(found, devig)
    if not body:
        if not response.get("games"):
            return _no_games(sport, market) + "\n" + credit_line(cost, _usage())

        lines = [f"No value on {market} for {sport} above {min_edge}%."]
        if consensus:
            lines.append(
                "A consensus needs four bookmakers pricing the same bet, and on "
                "markets with a line that means the same line. Fewer books "
                "quote each line of a totals, handicap or player prop market "
                "than quote the game itself, so this can mean too few prices "
                "rather than no value. Naming one book, devig='Pinnacle', "
                "needs only that book and is worth trying here."
            )
        else:
            lines.append(
                f"If {devig} does not price this market there is nothing to "
                f"compare against, which looks the same as finding nothing. "
                f"devig='all' prices against the other books instead."
            )
        lines.append(credit_line(cost, _usage()))
        return "\n".join(lines)

    return f"{body}\n{credit_line(cost, _usage())}"


def main() -> None:
    server.run()
