from __future__ import annotations

from app.sources.retail_live_adapter import GenericRetailLiveAdapter


class EbayMarketplaceAdapter(GenericRetailLiveAdapter):
    def __init__(self, client, category: str = "electronics") -> None:
        super().__init__(
            name="ebay_live",
            retailer="eBay",
            category=category,
            search_url_template="https://www.ebay.com/sch/i.html?_nkw={query}",
            client=client,
            source_role="marketplace",
            lane="marketplace",
            verification_state="seller_unverified",
            extraction_confidence="low",
            condition="used",
        )
