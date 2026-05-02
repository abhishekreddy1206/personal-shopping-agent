# Watch Alert Delivery Plan

## Goal
Use Babji/OpenClaw as the delivery channel for meaningful shopping alerts.

## Current local invocation
Babji can call:
- `app.shopping_service.handle_scheduled_watch_check()`

This returns formatted text summaries such as:
- current best observed offer
- threshold alerts like `below_target_price`

## Delivery rule
Babji should only forward alerts to Telegram when:
- a meaningful threshold or improvement occurred
- the alert is not a duplicate spam repeat
- the result confidence is adequate for the alert type

## Near-term improvement
Add alert dedupe keys and alert history checks before sending repeated watch-check notifications.
