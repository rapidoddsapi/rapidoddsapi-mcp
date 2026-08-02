# Changelog

Notable changes to this package. Versions follow [semantic versioning](https://semver.org).

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
