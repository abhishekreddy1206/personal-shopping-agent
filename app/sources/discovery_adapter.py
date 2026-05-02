from __future__ import annotations

from app.sources.retail_live_adapter import GenericRetailLiveAdapter


class DiscoverySearchAdapter(GenericRetailLiveAdapter):
    def __init__(self, *, name: str, retailer: str, category: str, search_url_template: str, client) -> None:
        super().__init__(
            name=name,
            retailer=retailer,
            category=category,
            search_url_template=search_url_template,
            client=client,
            source_role="discovery",
            lane="discovery",
            verification_state="signal_only",
            extraction_confidence="low",
            condition="unknown",
        )
