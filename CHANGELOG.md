# Changelog

Notable changes to this package. Versions follow [semantic versioning](https://semver.org).

## 0.1.0

First release.

- Five tools: `list_sports`, `get_odds`, `get_results`, `find_arbitrage`,
  `find_value_bets`
- Every response reports what it cost and the credits remaining
- A sport is always required, and bookmakers default to five, so a vague
  question costs 1 credit rather than tens
- Built on the `rapidoddsapi` SDK, which needs the API at v1.1.0 or later for
  the sport directory and balance lookups
