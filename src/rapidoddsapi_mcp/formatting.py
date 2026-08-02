"""Turn API responses into the text a model reads back.

Plain text rather than raw JSON, because these responses nest four levels deep
and the useful comparison, one selection priced across several books, is spread
across all of them. Flattening it is the difference between a model spotting
the best price and not.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from rapidoddsapi import group_games
from rapidoddsapi.types import Arbitrage, OddsResponse, ResultsResponse, Usage, ValueBet

# A selection is its name plus, on markets with a line, the line itself. Totals
# quote "Over" at several points and they are different bets.
Selection = tuple[str, float | None]


def credit_line(cost: int, usage: Usage | None) -> str:
    """The spend footer every tool ends with.

    Always present, so the model can see what it is burning and slow down on
    its own. `usage` is optional because a balance lookup failing should not
    take the actual answer down with it.
    """
    spent = f"Cost: {cost} credit{'s' if cost != 1 else ''}."

    if usage is None:
        return spent

    remaining = usage["credits_remaining"]
    limit = usage["credits_limit"]
    balance = f" Balance: {remaining:,} of {limit:,} remaining."
    if not usage["resets"]:
        balance += " These do not reset."
    return spent + balance


def format_odds(response: OddsResponse, bookmakers: Sequence[str]) -> str:
    """Odds grouped by game, then market, then selection, best price first.

    The API returns one entry per bookmaker, so the same fixture arrives once
    per book. `group_games` merges them on teams plus a time window, which is
    what makes the cross book comparison possible at all. A window rather than
    an equality check because books disagree on the start time, sometimes by
    an hour.
    """
    if not response.get("games"):
        return ""

    games = group_games(response)
    books = ", ".join(bookmakers)
    lines = [f"{response.get('sport', 'Unknown')} — {len(games)} game(s), from {books}", ""]

    for entry in games:
        game = entry["game"]
        lines.append(f"{game.get('away_team')} at {game.get('home_team')}  {_when(game)}")

        for market, prices in _by_market(entry).items():
            lines.append(f"  {market}")
            for (name, point), quotes in prices.items():
                quotes.sort(key=lambda q: q[0], reverse=True)
                label = name if point is None else f"{name} {point:+g}"
                best_price, best_book = quotes[0]
                rest = ", ".join(f"{book} {price}" for price, book in quotes[1:])
                line = f"    {label:<28} {best_price} ({best_book})"
                lines.append(f"{line}   {rest}" if rest else line)
        lines.append("")

    return "\n".join(lines).rstrip()


def selection_label(bet: Mapping[str, Any]) -> str:
    """Name a bet in full, so two sides of one line cannot be confused.

    On a market with a line both sides are called "Over" and "Under", and on
    props and team totals several bets share those names, so the subject and
    the line have to be shown or the legs read as duplicates. Only a handicap
    is signed: "Over +8.5" implies the line itself is positive, where on a
    handicap the sign is the whole meaning.
    """
    name = str(bet.get("team") or bet.get("selection", ""))
    parts = [bet.get("player_name"), bet.get("team_name"), name]

    point = bet.get("point")
    if point is not None:
        parts.append(f"{point:g}" if name in ("Over", "Under") else f"{point:+g}")

    return " ".join(str(part) for part in parts if part)


def format_arbitrage(found: list[Arbitrage], stake: float) -> str:
    if not found:
        return ""

    lines = [f"{len(found)} arbitrage opportunit{'y' if len(found) == 1 else 'ies'}:", ""]
    for arb in found:
        lines.append(
            f"{arb['away_team']} at {arb['home_team']}  {arb['profit_percent']:+.2f}% "
            f"on a {stake:g} stake"
        )
        for leg in arb["legs"]:
            lines.append(
                f"    {selection_label(leg):<34} {leg['price']} @ {leg['bookmaker']}  "
                f"stake {leg['stake']:g}"
            )
        lines.append("")

    lines.append(
        "Prices move while the second leg is being placed, so an edge this small "
        "may not survive. Check both are still live before betting."
    )
    return "\n".join(lines)


def format_value_bets(found: list[ValueBet], devig: str) -> str:
    if not found:
        return ""

    against = "every bookmaker" if devig == "all" else devig
    lines = [f"{len(found)} value bet(s), priced against {against}:", ""]
    for bet in found:
        lines.append(
            f"+{bet['edge_percent']:.2f}%  {selection_label(bet)} "
            f"{bet['price']} @ {bet['bookmaker']}"
        )
        lines.append(
            f"    {bet['away_team']} at {bet['home_team']}  "
            f"fair price {bet['fair_price']:.2f} "
            f"({bet['fair_probability'] * 100:.1f}% implied)"
        )
    lines.append("")
    lines.append(
        f"Edge is measured off {against} with the margin removed. It is an estimate of "
        "value, not a guaranteed win."
    )
    return "\n".join(lines)


def format_results(response: ResultsResponse) -> str:
    games = response.get("games", [])
    if not games:
        return ""

    lines = [f"{response.get('sport', 'Unknown')} — {len(games)} game(s)", ""]

    for game in games:
        info = game.get("game", {})
        status = info.get("status", "UNKNOWN")
        lines.append(
            f"{info.get('away_team')} at {info.get('home_team')}  [{status}]  {_when(info)}"
        )

        score = game.get("score")
        if score:
            lines.extend(_score_lines(score))

        players = game.get("players")
        if players:
            lines.append(f"    player stats for {len(players)} player(s)")
        lines.append("")

    lines.append(
        "A named total (half_time, full_time) stays null until that period is "
        "complete. For a live running total, sum the by_period values."
    )
    return "\n".join(lines)


def _score_lines(score: Mapping[str, Any]) -> list[str]:
    """Scores exactly as the sport reports them.

    Scoring fields differ by sport, AFL counting goals, behinds and points
    where MLB counts runs and hits, so the field names are passed through
    rather than mapped onto a guessed "the score". Nothing here needs to know
    which sport it is looking at.
    """
    lines = []

    for side in ("away", "home"):
        team = score.get(side) or {}
        stats = _stats(team)
        if stats:
            lines.append(f"    {team.get('team', side)}: {stats}")

    totals = score.get("totals") or {}
    for key in ("full_time", "half_time", "first_5_innings"):
        value = totals.get(key)
        if isinstance(value, dict) and value:
            lines.append(f"    {key} (both teams): {_stats(value)}")

    state = score.get("period_state") or []
    if state:
        done = sum(1 for period in state if period.get("completed"))
        lines.append(f"    periods: {done} of {len(state)} complete")

    return lines


def _stats(values: Mapping[str, Any]) -> str:
    return ", ".join(f"{key} {value}" for key, value in values.items() if key != "team")


def _by_market(entry: Mapping[str, Any]) -> dict[str, dict[Selection, list[tuple[float, str]]]]:
    """Invert bookmaker -> market -> outcome into market -> selection -> prices."""
    markets: dict[str, dict[Selection, list[tuple[float, str]]]] = {}

    for book in entry.get("bookmakers", []):
        for market in book.get("markets", []):
            key = market.get("key", "unknown")
            for outcome in market.get("outcomes", []):
                price = outcome.get("price")
                if price is None:
                    continue
                name = outcome.get("player_name") or outcome.get("name", "")
                selection: Selection = (name, outcome.get("point"))
                markets.setdefault(key, {}).setdefault(selection, []).append(
                    (price, book.get("name", "?"))
                )

    return markets


def _when(game: Mapping[str, Any]) -> str:
    """Timestamps are naive UTC with no offset, so the zone is stated explicitly."""
    raw = game.get("commence_time") or game.get("start_time")
    if not raw:
        return ""
    return f"({raw.replace('T', ' ')} UTC)"
