"""Which bookmakers to ask for, and the futures market keys.

With no bookmakers named, every feed is requested. Feeds price across regions,
an Australian book carries the NFL and Bet365 is the only NCAAF feed, so any
smaller default would leave out books that price the game. Credits are
`market_types x ceil(bookmakers / 5)`, so every feed costs more than a few
named ones; the tool descriptions say so.
"""

from collections.abc import Sequence

from rapidoddsapi import AU_BOOKMAKERS, BOOKMAKERS, EU_BOOKMAKERS, EXCHANGES, US_BOOKMAKERS

# Shorthands accepted in a bookmakers list, matched without regard to case and
# mixable with plain names: ["AU", "Pinnacle"].
GROUPS: dict[str, Sequence[str]] = {
    "ALL": BOOKMAKERS,
    "AU": AU_BOOKMAKERS,
    "US": US_BOOKMAKERS,
    "EU": EU_BOOKMAKERS,
    "EXCHANGES": EXCHANGES,
}

# Futures market keys. The API has no endpoint listing them, unlike match
# markets, so without this the model would have to guess, and a guessed key
# returns nothing rather than an error. Season-specific keys such as
# brownlow_medal_winner_without_daicos are left out, since they are replaced
# each year. Source: the futures block on rapidoddsapi.com/coverage.
FUTURES_MARKETS = {
    "AFL": (
        "premiership_winner",
        "brownlow_medal_winner",
        "brownlow_medal_top_3_finish",
        "brownlow_medal_top_5_finish",
        "brownlow_medal_top_10_finish",
        "brownlow_medal_top_20_finish",
        "brownlow_medal_most_games_polled",
        "brownlow_medal_most_3_vote_games",
        "brownlow_medal_most_votes_last_8_rounds",
        "brownlow_medal_leader_after_round_6",
        "brownlow_medal_leader_after_round_10",
        "brownlow_medal_leader_after_round_15",
        "brownlow_player_season_votes",
        "brownlow_club_season_votes",
        "brownlow_player_season_votes_milestones",
        "brownlow_3_votes",
    ),
}


def all_bookmakers() -> Sequence[str]:
    """Every feed, for every sport.

    The API has no bookmaker endpoint and does not validate the names, so a
    name that is not a feed returns an empty result rather than an error.
    Without this list the only way to discover a feed is to guess and pay for
    the attempt, so it has to be handed over up front.
    """
    return BOOKMAKERS


def resolve_bookmakers(requested: Sequence[str] | None) -> list[str]:
    """Expand group names, keep plain names, and default to every feed.

    Order is kept and duplicates dropped, so ["AU", "US"] does not request
    Bet365 twice and pay for it in the credit count.
    """
    if not requested:
        return list(BOOKMAKERS)

    books: list[str] = []
    for entry in requested:
        for book in GROUPS.get(entry.strip().upper(), (entry,)):
            if book not in books:
                books.append(book)
    return books


def with_devig_book(bookmakers: Sequence[str], book: str) -> list[str]:
    """Guarantee the book value is measured against is in the list.

    Without it there is nothing to de-vig, so the request would be paid for and
    return nothing.
    """
    if book in bookmakers:
        return list(bookmakers)
    return [book, *bookmakers]
