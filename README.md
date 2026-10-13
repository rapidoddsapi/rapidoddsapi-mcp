# rapidoddsapi-mcp

MCP server for [RapidOddsAPI](https://rapidoddsapi.com). Gives an AI assistant
bookmaker odds, futures, live scores, arbitrage and value bets.

Built on the official [`rapidoddsapi`](https://pypi.org/project/rapidoddsapi)
Python SDK.

## Setup

You need an API key from the [dashboard](https://rapidoddsapi.com/dashboard).
Keys start with `oa_`.

### Claude Desktop

Add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "rapidoddsapi": {
      "command": "uvx",
      "args": ["rapidoddsapi-mcp"],
      "env": {
        "RAPIDODDSAPI_API_KEY": "oa_your_api_key_here"
      }
    }
  }
}
```

The config file lives at `~/Library/Application Support/Claude/` on macOS and
`%APPDATA%\Claude\` on Windows. Restart Claude Desktop after editing it.

### Anything else that speaks MCP

```bash
RAPIDODDSAPI_API_KEY=oa_your_api_key_here uvx rapidoddsapi-mcp
```

It speaks stdio.

## Tools

| Tool | Credits |
|---|---|
| `list_sports(sport=)` | 0 |
| `get_odds(sport, market_types=, bookmakers=)` | `market_types x ceil(bookmakers / 5)` |
| `get_futures(sport, market_types, bookmakers=, season=)` | `market_types x ceil(bookmakers / 5)` |
| `get_results(sport, status=, include=)` | 1 |
| `find_arbitrage(sport, market=, bookmakers=, min_profit=, stake=)` | `ceil(bookmakers / 5)` |
| `find_value_bets(sport, market=, bookmakers=, min_edge=, devig=)` | `ceil(bookmakers / 5)` |

Credits are charged only when games come back, so a query that matches nothing
is free. Every response ends with what it cost and what is left.

## Credits

Credits are one per market type per five bookmakers.

- A sport is always required. There is no way to request every sport at once.
- Market types default to one.
- Bookmakers default to every feed, about 6 credits per market type. Feeds
  price across regions, an Australian book carries the NFL, so a regional
  default would leave out books that price the game.

To narrow a request, name books or a group: `"AU"`, `"US"`, `"EU"` or
`"EXCHANGES"`, mixable with names, as in `["AU", "Pinnacle"]`. Asking for
"Australian books only" is enough; the model passes the group.

The free tier is 250 credits for the life of the account, with no monthly
reset. The tool descriptions state the cost, so the model can say what a
request will cost before making an expensive one.

## Markets

`find_arbitrage` and `find_value_bets` handle any market whose bets have two
sides: `head_to_head` and its period variants, soccer's `draw_no_bet`, totals,
handicaps, team totals and player props. Each line is its own bet, so a totals
market can return several results for one game.

Three-way markets return an error explaining why rather than an empty list,
since "nothing found" would read as "no opportunities".

`find_value_bets` takes `devig` for where the fair price comes from. The
default, `"all"`, de-vigs every bookmaker fetched and averages the result,
which needs no view on which book is sharp. Naming one, `devig="Pinnacle"`,
measures every other book against that one instead: tighter, but only on
markets that book prices. A consensus needs four bookmakers on the same line,
so on thin markets naming a book finds bets that averaging cannot.

Market keys vary by sport. `list_sports(sport)` returns the valid ones and
costs nothing.

Winning margin and other markets priced in bands cannot be paired, so
`find_arbitrage` and `find_value_bets` say so rather than reporting that they
found nothing. `get_odds` still compares them across books.

## Futures

Season-long outrights, such as the Brownlow Medal and AFL Premiership, come
from `get_futures` rather than `get_odds`. They have their own market keys,
which `list_sports("AFL")` lists separately from the match ones. Long fields
are cut to the favourites, with a count of the rest.

## Bookmakers

Names are odds feeds, not brands. Many brands share one feed and quote
identical prices, so `Ladbrokes` covers Neds and `Betmakers` covers the 26
brands running on it. A brand name that is not a feed returns nothing.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy src/rapidoddsapi_mcp
```

## Links

- [RapidOddsAPI](https://rapidoddsapi.com)
- [Documentation](https://rapidoddsapi.com/docs)
- [Coverage: sports, bookmakers, market keys](https://rapidoddsapi.com/coverage)
- [Python SDK](https://github.com/rapidoddsapi/rapidoddsapi-python)

## License

MIT
