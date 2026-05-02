# Source Policy

## Trust tiers

### High trust
- Official brand/manufacturer sites
- Major first-party retailers
- Direct product pages
- Direct store promotion pages

### Medium trust
- Reputable comparison pages
- Established price-history/trend pages
- Known deal communities with recency signals
- Large marketplaces when seller-quality filters are applied

### Low trust
- Random coupon blogs
- SEO coupon farms
- Weakly sourced affiliate listicles
- Unverified third-party reseller pages

## Source roles

### Truth sources
These are eligible for default purchase recommendations:
- Amazon
- Best Buy
- Walmart
- Target
- Costco
- Newegg
- B&H
- Nike / Adidas / direct brand sites

### Discovery sources
These provide deal signals, historical context, and alternate opportunities:
- Slickdeals
- price-history sites
- trusted deal communities
- shopping-discovery aggregators

Rule: discovery sources must not become top recommendations without corroboration.

### Marketplace sources
These are opt-in and should be ranked separately:
- eBay
- Facebook Marketplace
- OfferUp
- Mercari
- StockX / GOAT when relevant

Rule: marketplace mode requires additional scoring on seller reputation, item condition, and shipping/local-pickup risk.

### Enrichment sources
These can modify effective-price context but are not truth sources:
- cashback portals
- public coupon sites
- retailer promo pages
- email/newsletter discounts when explicitly applicable

Rule: all coupon claims must carry a confidence score and, when possible, an evidence path.

## Robustness rules
- Fail closed: if extraction confidence is too low, suppress the result instead of bluffing.
- Preserve raw snapshots for live extraction sources when feasible.
- Use short timeouts with deterministic fallback behavior.
- Separate ranking lanes for trusted retail vs marketplace.
- Expose `confidence`, `source_mode`, and `has_snapshot` in outputs.
