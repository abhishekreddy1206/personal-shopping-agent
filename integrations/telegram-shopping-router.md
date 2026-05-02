# Telegram Shopping Router Plan

## Goal
Route Telegram shopping requests into the personal-shopping-agent project while keeping all execution local.

## Integration shape
- Main Babji session remains the Telegram-facing entry point.
- Shopping-specific messages are delegated into the local project runner/service.
- Responses are returned to the same Telegram chat.
- Scheduled watch checks can later emit Telegram alerts back through Babji/OpenClaw.

## Why this shape
This avoids building a separate unsafe bot stack. OpenClaw already owns Telegram ingress and message delivery. The shopping project should own domain logic, persistence, and watch/trend behavior.

## Phase 1 integration contract
- Telegram message arrives in Babji.
- Babji detects shopping intent.
- Babji invokes the shopping agent project locally.
- Project returns structured JSON.
- Babji reformats it into a user-facing Telegram response.

## Phase 2 integration contract
- Local scheduled watch checks run.
- If an alert is meaningful, Babji sends a Telegram notification.

## Security notes
- No direct external bot rewrite from the project.
- No secrets stored in project code.
- Telegram delivery stays under OpenClaw control.
- Shopping project remains local-only.
