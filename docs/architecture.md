# Personal Shopping Agent — Engineering Design Doc

## Overview
Build a personal Telegram-native shopping agent for Abhishek that can search trusted retailers, compare offers, store search history, maintain watchlists, monitor price drops, and improve recommendations over time using observed trends and feedback.

## Expanded source model
The system should separate sources by role instead of treating every site as equally trustworthy.

### Layer 1 — trusted retail truth sources
Use for core purchase recommendations:
- Amazon
- Best Buy
- Walmart
- Target
- Costco
- Newegg
- B&H
- Nike / Adidas / brand-direct
- manufacturer direct sites

### Layer 2 — discovery and trend sources
Use for finding opportunities, historical context, and deal signals:
- Slickdeals
- price-history / trend sites
- trusted deal communities
- Google Shopping-style discovery sources

These should influence search coverage and buy/wait guidance, but should not outrank trusted retailer offers without verification.

### Layer 3 — marketplace mode
Use only in a separate bargain-hunting mode:
- eBay
- Facebook Marketplace
- OfferUp
- Mercari
- StockX / GOAT for relevant categories

These require special treatment for seller quality, condition, shipping risk, and return policy. Marketplace results should not be merged into default trusted-retail rankings.

### Layer 4 — coupon and cashback enrichment
Use only as enrichment, never as the sole truth source:
- store promo pages
- RetailMeNot-style public code sources
- Rakuten / cashback portals
- newsletter/signup discounts

Coupon claims must be confidence-scored and clearly labeled.

## Robust flow model
### Search modes
1. `trusted_only`
2. `trusted_plus_discovery`
3. `trusted_plus_marketplace`
4. `aggressive_deal_hunt`

Default mode should be `trusted_plus_discovery` for deal-seeking without marketplace risk.

### Execution phases
1. Parse intent and extract constraints
2. Select source mode
3. Query trusted retail sources
4. Optionally query discovery sources
5. Optionally query marketplace sources in separate ranking lane
6. Normalize and deduplicate offers
7. Score offers with trust-aware ranking
8. Attach trend/coupon context with confidence labels
9. Decide buy-now / watch-later / marketplace-only recommendations

## Robustness rules
- Never let discovery-only sources outrank verified retailer offers automatically.
- Never let marketplace offers outrank retail offers unless marketplace mode is enabled.
- Always label source mode, confidence, and snapshot availability.
- Prefer omission over false precision when extraction confidence is low.
- Degrade gracefully when live fetch fails.
- Keep timeouts short and maintain fallback behavior.

## Success criteria additions
- Deal-discovery sources improve coverage without increasing junk recommendations.
- Marketplace mode remains opt-in and separately ranked.
- Coupon/trend signals are visible but clearly confidence-scored.
- The agent explains whether a result came from trusted retail, discovery, or marketplace mode.
