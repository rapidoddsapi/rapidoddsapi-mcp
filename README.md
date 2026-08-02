# rapidoddsapi-mcp

MCP server for [RapidOddsAPI](https://rapidoddsapi.com). Gives an AI assistant
bookmaker odds, live scores, arbitrage and value bets.

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
| `get_results(sport, status=, include=)` | 1 |
| `find_arbitrage(sport, market=, bookmakers=, min_profit=, stake=)` | `ceil(bookmakers / 5)` |
| `find_value_bets(sport, market=, bookmakers=, min_edge=, sharp=)` | `ceil(bookmakers / 5)` |

Credits are charged only when games come back, so a query that matches nothing
is free. Every response ends with what it cost and what is left.

## Credits

The free tier is 250 credits for the life of the account, with no monthly
reset, so the defaults are deliberately narrow:

- A sport is always required. There is no way to request every sport at once.
- Bookmakers default to five, one credit group, chosen for the sport's region.
- Market types default to one.

That makes a typical question cost 1 credit. Both arguments multiply, so asking
for nine market types across eighteen bookmakers is 36. The tool descriptions
say so, which is what keeps the model from doing it uninvited.

`find_arbitrage` and `find_value_bets` default to ten bookmakers, 2 credits,
because both need books that disagree and five rarely spread far enough.

## Markets

`find_arbitrage` and `find_value_bets` handle two-way markets with no line:
`head_to_head`, its period variants, and soccer's `draw_no_bet`. Totals,
spreads, player props and three-way markets return an error explaining why
rather than an empty list, since "nothing found" would read as "no
opportunities".

Market keys vary by sport. `list_sports(sport)` returns the valid ones and
costs nothing.

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
