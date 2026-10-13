# Changelog

Notable changes to this package. Versions follow [semantic versioning](https://semver.org).

## 0.4.0

Needs the SDK at 0.4.0 or later.

- `get_futures` for season-long outrights such as the Brownlow Medal and AFL
  Premiership. `list_sports(sport)` lists the futures keys separately from the
  match ones, and `list_sports()` marks which sports have futures
- NCAAF, NBL, AFLW, NRLW and the per-tournament ATP ids come through from the
  SDK
- Bookmakers default to every feed rather than five picked by region. Feeds
  price across regions, an Australian book carries the NFL and Bet365 is the
  only NCAAF feed, so a regional default left out books pricing the game. A
  default request now costs about 6 credits per market type instead of 1
- `bookmakers` accepts `"AU"`, `"US"`, `"EU"` and `"EXCHANGES"` as groups,
  mixable with names
- `get_odds` keeps player props, team totals and winning margin bands apart.
  Grouped on the player and line alone, a player's Over and Under merged into
  one row, both teams' totals did the same, and the best price shown could
  belong to the other side
- `find_arbitrage` and `find_value_bets` explain that a banded market such as
  winning margin cannot be paired, rather than reporting no opportunities

## 0.3.0

Needs the SDK at 0.3.0 or later.

- `find_arbitrage` and `find_value_bets` work on totals, handicaps, team totals
  and player props, not only two-way markets with no line. Their descriptions
  said otherwise, so the model was turning down markets that now work. Only
  three-way markets are still refused
- `find_value_bets` takes `devig` in place of `sharp`. The default, `"all"`,
  de-vigs every bookmaker fetched and averages the result, which needs no view
  on which book is sharp and works on markets Pinnacle does not price. Naming
  a book measures the others against it, as before. The description explains
  the trade-off so the model can put it to the user rather than pick silently
- Nothing is seeded into the bookmaker list under `"all"`, since a consensus
  needs enough books rather than any particular one. Naming a book still seeds
  it, or the request is paid for and cannot be de-vigged
- An empty consensus says four bookmakers have to price the same line, and
  suggests naming a book. Fewer books quote each line of a totals or player
  prop market than quote the game, so a thin market otherwise reads as no value
- Arbitrage legs and value bets show the line and the player or team, so two
  sides of a totals bet no longer both read "Over". Handicaps are signed,
  totals are not, since "Over +8.5" implies the line itself is positive
- An empty result from `find_arbitrage` or `find_value_bets` says when no games
  came back at all, rather than reporting that it looked and found nothing. A
  sport out of season read as "no arbitrage", which is a conclusion that was
  never tested
- A near miss prints as `-0.90%` rather than `+-0.90%`
- `list_sports(sport)` returns every bookmaker rather than only the sport's
  region. Feeds price across regions, so an American book quoting the AFL is
  normal and hiding it removed a real option for line shopping
- An empty `get_odds` now says whether the market types are wrong for the
  sport. The API returns nothing for a market it does not recognise, which was
  indistinguishable from the season being over

## 0.2.0

- `list_sports(sport)` now returns every bookmaker that can be requested for
  that sport, alongside its market types. There was no way to discover a
  bookmaker name: the API has no endpoint for them and does not reject unknown
  ones, it just returns no prices. A model asked which bookmakers were covered
  would therefore guess names and pay for each attempt, and a casing slip such
  as `Palmerbet` for `PalmerBet` looked identical to the book not existing
- Tool descriptions say not to guess bookmaker or market names, and where the
  valid ones come from
- Soccer and tennis now list every feed rather than only the European ones,
  since Australian and American books price them too

## 0.1.2

- Certificates are verified against the operating system's trust store. On
  networks that inspect HTTPS, and with antivirus that does the same, every
  request previously failed with CERTIFICATE_VERIFY_FAILED because the bundled
  store does not know the intercepting certificate the machine itself trusts

## 0.1.1

- Tool descriptions now say these tools are RapidOddsAPI itself. Asked what
  RapidOddsAPI covered, a model would search the web instead of calling
  `list_sports`, because nothing connected the name to the tools

## 0.1.0

First release.

- Five tools: `list_sports`, `get_odds`, `get_results`, `find_arbitrage`,
  `find_value_bets`
- Every response reports what it cost and the credits remaining
- A sport is always required, and bookmakers default to five, so a vague
  question costs 1 credit rather than tens
- Built on the `rapidoddsapi` SDK, which needs the API at v1.1.0 or later for
  the sport directory and balance lookups
