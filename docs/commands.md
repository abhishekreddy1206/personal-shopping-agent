# Telegram Command and Intent Surface

## Natural language intents
- Find me the best deal on Sony WH-1000XM6
- Best men's running shoes under $120
- Track this monitor if it drops below $280
- Show my recent shopping searches
- Show my watchlist
- What dropped today?
- Should I buy now or wait?
- Search in marketplace mode for used Sony headphones
- Hunt aggressively for deals on a 27 inch 4k monitor

## Optional explicit commands
- `/shop find <query>`
- `/shop watch <query>`
- `/shop history`
- `/shop watchlist`
- `/shop dropped`
- `/shop status`
- `/shop mode trusted_only <query>`
- `/shop mode trusted_plus_discovery <query>`
- `/shop mode trusted_plus_marketplace <query>`
- `/shop mode aggressive_deal_hunt <query>`

## Intent types
- `search`
- `watch_create`
- `history_lookup`
- `watchlist_view`
- `drop_summary`
- `buy_or_wait`

## Parsing targets
- category
- product terms
- budget min/max
- target price
- size/color/condition
- urgency
- preferred retailers
- excluded retailers
- source mode
