"""Which bookmakers to ask for when the caller does not say.

Credits are `market_types x ceil(bookmakers / 5)`, so five bookmakers is one
group and the cheapest useful request. Picking them by region matters: asking
US books about the AFL returns nothing and still risks a charge on another
sport, and line shopping only works across books that actually price the game.
"""

from collections.abc import Sequence

# Five per region, one credit group. Deliberately mixed rather than the five
# biggest, since arbitrage and value both need books that disagree.
AU_DEFAULT = ("Sportsbet", "TAB", "Ladbrokes", "Bet365", "Pointsbet")
US_DEFAULT = ("DraftKings", "BetMGM", "Fanatics", "Bet365", "Bovada")
EU_DEFAULT = ("Pinnacle", "Bet365", "Unibet", "Sportsbet", "TAB")

_REGIONS = {
    "AFL": AU_DEFAULT,
    "NRL": AU_DEFAULT,
    "NFL": US_DEFAULT,
    "NBA": US_DEFAULT,
    "WNBA": US_DEFAULT,
    "MLB": US_DEFAULT,
    "NHL": US_DEFAULT,
}

# Soccer and tennis are priced best by the European books, and every sport not
# named above falls into that bucket.
_FALLBACK = EU_DEFAULT

# A sharp book prices close to true probability, which is what value betting
# measures against. Pinnacle is the one this API carries.
SHARP_BOOKMAKER = "Pinnacle"

# Arbitrage needs disagreement between books, so it looks wider than a plain
# odds request. Ten books is two credit groups.
ARBITRAGE_DEFAULT_COUNT = 10


def default_bookmakers(sport: str) -> tuple[str, ...]:
    """The five books to use for a sport when the caller did not choose."""
    return _REGIONS.get(sport.upper(), _FALLBACK)


def all_bookmakers() -> Sequence[str]:
    """Every feed, for every sport.

    Not filtered by region. Feeds price across regions, so an American book
    quoting the AFL is normal, and hiding it would remove a real option for
    line shopping.

    The API has no bookmaker endpoint and does not validate the names, so a
    name that is not a feed returns an empty result rather than an error.
    Without this list the only way to discover a feed is to guess and pay for
    the attempt, so it has to be handed over up front.
    """
    from rapidoddsapi import BOOKMAKERS

    return BOOKMAKERS


def wide_bookmakers(
    sport: str,
    count: int = ARBITRAGE_DEFAULT_COUNT,
    must_include: Sequence[str] = (),
) -> Sequence[str]:
    """A wider spread for the tools that compare books against each other.

    Starts from the sport's region, then tops up from the other regions with
    feeds that carry most sports, skipping duplicates.

    `must_include` is seeded first and counts towards the total rather than
    being added on top, so requiring the sharp book does not quietly push the
    list over a credit group boundary.
    """
    from rapidoddsapi import AU_BOOKMAKERS, EU_BOOKMAKERS, US_BOOKMAKERS

    region = default_bookmakers(sport)
    region_pool: dict[tuple[str, ...], Sequence[str]] = {
        AU_DEFAULT: AU_BOOKMAKERS,
        US_DEFAULT: US_BOOKMAKERS,
        EU_DEFAULT: EU_BOOKMAKERS,
    }

    picked = list(must_include)
    picked += [book for book in region if book not in picked]
    first = region_pool[region]
    for pool in (first, EU_BOOKMAKERS, AU_BOOKMAKERS, US_BOOKMAKERS):
        for book in pool:
            if len(picked) >= count:
                return picked
            if book not in picked:
                picked.append(book)

    return picked


def with_sharp(bookmakers: Sequence[str], book: str = SHARP_BOOKMAKER) -> Sequence[str]:
    """Guarantee the book value is measured against is in the list.

    Without it there is nothing to de-vig, so the request would be paid for and
    return nothing.
    """
    if book in bookmakers:
        return bookmakers
    return [book, *bookmakers]
