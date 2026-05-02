# Live Babji Routing Behavior

## Goal
Make Babji the live Telegram front door while the shopping project stays the local domain engine.

## Desired runtime behavior
1. Telegram message arrives in Babji.
2. Babji checks `app.shopping_service.should_handle(text)`.
3. If false, Babji handles the message normally.
4. If true, Babji calls `app.shopping_service.handle_message(text)`.
5. Babji sends the returned text back to Telegram.

## Scheduled watch behavior
1. A local scheduled task invokes `app.shopping_service.handle_scheduled_watch_check()`.
2. Babji receives the returned text.
3. Babji forwards only meaningful, non-duplicate alerts.

## Delivery rules
- Do not send duplicate watch alerts repeatedly.
- Suppress low-confidence alert candidates.
- Keep Telegram messages concise and user-facing.
- Preserve OpenClaw as the only delivery system.

## Near-term implementation guidance
- Add duplicate alert history checks before forwarding watch-check summaries.
- Keep shopping routing explicit; avoid over-triggering on unrelated messages.
