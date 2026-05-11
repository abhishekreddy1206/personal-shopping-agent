from __future__ import annotations

from app.formatting import format_result
from app.models.types import ExecutionResult, OfferCandidate, ParsedIntent, RankedOffer
from app.orchestrator.shopping_orchestrator import ShoppingOrchestrator
from app.ranking.ranker import Ranker
from app.sources.registry import SourceRegistry
from app.sources.live_fetch import LiveFetchClient, extract_amazon_candidate
from app.sources.search_utils import analyze_listing_text, choose_best_lines, suppress_stub_offers, title_match_score


def test_title_match_prefers_model_number() -> None:
    intent = ParsedIntent(
        intent_type="search",
        raw_query="Find me Sony WH-1000XM6 headphones",
        category="electronics",
        filters={"model_number": "WH-1000XM6"},
    )
    exact = title_match_score("Sony WH-1000XM6 Wireless Noise Canceling Headphones", intent)
    loose = title_match_score("Sony CH-720N Wireless Headphones", intent)
    assert exact > loose
    assert exact > 0.7


def test_suppress_stub_offers_drops_every_stub_unconditionally() -> None:
    """Policy: only real web-sourced prices reach the user. Stubs are filtered at the
    registry boundary regardless of whether any live offer exists alongside them."""
    live = OfferCandidate(
        source_name="amazon_live",
        retailer="Amazon",
        listing_url="https://example.com/live",
        title="Sony WH-1000XM6",
        effective_price=299.99,
        metadata={"source_mode": "live_extract", "lane": "trusted_retail"},
    )
    trusted_stub = OfferCandidate(
        source_name="amazon",
        retailer="Amazon",
        listing_url="https://example.com/stub",
        title="Sony WH-1000XM6 stub",
        effective_price=309.99,
        metadata={"source_mode": "fallback_stub", "lane": "trusted_retail"},
    )
    marketplace_stub = OfferCandidate(
        source_name="ebay",
        retailer="eBay",
        listing_url="https://example.com/stub",
        title="Sennheiser HD 650 used",
        effective_price=199.0,
        metadata={"source_mode": "fallback_stub", "lane": "marketplace"},
        source_role="marketplace",
    )
    assert suppress_stub_offers([live, trusted_stub, marketplace_stub]) == [live]
    assert suppress_stub_offers([trusted_stub, marketplace_stub]) == []


def test_ranker_prefers_trusted_retail_over_marketplace_signal() -> None:
    retail = OfferCandidate(
        source_name="best_buy_live",
        retailer="Best Buy",
        listing_url="https://example.com/bb",
        title="Sony WH-1000XM6",
        effective_price=319.99,
        condition="new",
        metadata={"lane": "trusted_retail", "match_score": 0.95},
        source_role="truth",
        verification_state="unverified",
    )
    market = OfferCandidate(
        source_name="ebay_live",
        retailer="eBay",
        listing_url="https://example.com/ebay",
        title="Sony WH-1000XM6",
        effective_price=279.99,
        condition="used",
        metadata={"lane": "marketplace", "match_score": 0.95},
        source_role="marketplace",
        verification_state="seller_unverified",
    )
    ranked = Ranker().rank([market, retail])
    assert ranked[0].offer.retailer == "Best Buy"
    assert ranked[0].label == "best_verified_retail"


def test_accessory_and_generic_lines_are_suppressed_for_exact_model_search() -> None:
    intent = ParsedIntent(
        intent_type="search",
        raw_query="Find me the best deal on Sony WH-1000XM6",
        category="electronics",
        filters={"model_number": "WH-1000XM6", "brand": "Sony"},
    )
    accessory = analyze_listing_text("Sony WH-1000XM6 replacement earpads case", intent)
    generic = analyze_listing_text('"Find me the best deal on Sony WH-1000XM6" : Target', intent)
    assert accessory["is_accessory"] is True
    assert generic["is_generic"] is True


def test_choose_best_lines_prefers_exact_priced_listing() -> None:
    intent = ParsedIntent(
        intent_type="search",
        raw_query="Find me the best deal on Sony WH-1000XM6",
        category="electronics",
        filters={"model_number": "WH-1000XM6", "brand": "Sony"},
    )
    text = """
    Sony WH-1000XM6 Wireless Noise Canceling Headphones
    $398.00
    Sony WH-1000XM6 replacement earpads case
    $19.99
    \"Find me the best deal on Sony WH-1000XM6\" : Target
    Sony WH-1000XM5 Wireless Headphones
    $299.99
    """
    candidates = choose_best_lines(text, intent)
    assert len(candidates) == 1
    assert candidates[0][0] == "Sony WH-1000XM6 Wireless Noise Canceling Headphones"
    assert candidates[0][1] == 398.0
    assert candidates[0][3]["exact_model_match"] is True


def test_retail_live_adapter_can_require_price_for_noisy_retailers(tmp_path) -> None:
    from app.sources.retail_live_adapter import GenericRetailLiveAdapter

    class StubClient(LiveFetchClient):
        def __init__(self) -> None:
            super().__init__(tmp_path)

        def fetch_text(self, url: str) -> str:
            return """
            Search Newegg.com for Find me the best deal on Sony WH-1000XM6. Get fast shipping and top-rated customer service.
            Sony WH-1000XM6 Wireless Noise Canceling Headphones
            """

    intent = ParsedIntent(
        intent_type="search",
        raw_query="Find me the best deal on Sony WH-1000XM6",
        category="electronics",
        filters={"model_number": "WH-1000XM6", "brand": "Sony", "product_text": "Sony WH-1000XM6"},
    )
    adapter = GenericRetailLiveAdapter(
        name="newegg_live",
        retailer="Newegg",
        category="electronics",
        search_url_template="https://www.newegg.com/p/pl?d={query}",
        client=StubClient(),
        require_price=True,
    )
    assert adapter.search(intent) == []


def test_retail_live_adapter_can_infer_price_from_neighboring_lines(tmp_path) -> None:
    from app.sources.retail_live_adapter import GenericRetailLiveAdapter

    class StubClient(LiveFetchClient):
        def __init__(self) -> None:
            super().__init__(tmp_path)

        def fetch_text(self, url: str) -> str:
            return """
            Samsung LS03D 43\" Class The Frame QLED 4K Smart TV (2024) - QN43LS03DAFXZA
            Save: $300.00 (20%)
            Now: $699.99
            Samsung LS03D 50\" Class The Frame QLED 4K Smart TV (2024) - QN50LS03DAFXZA
            Limited time price: $799.99
            """

    intent = ParsedIntent(
        intent_type="search",
        raw_query="Find me the best deal on Samsung The Frame TV 55 inch",
        category="electronics",
        filters={"brand": "Samsung", "product_family": "the frame tv", "product_text": "Samsung The Frame Tv", "size": "55 inch"},
    )
    adapter = GenericRetailLiveAdapter(
        name="newegg_live",
        retailer="Newegg",
        category="electronics",
        search_url_template="https://www.newegg.com/p/pl?d={query}",
        client=StubClient(),
        require_price=True,
    )
    offers = adapter.search(intent)
    assert len(offers) >= 2
    assert offers[0].effective_price == 699.99
    assert offers[1].effective_price == 799.99


def test_retail_live_adapter_filters_implausible_headphone_prices(tmp_path) -> None:
    from app.sources.retail_live_adapter import GenericRetailLiveAdapter

    class StubClient(LiveFetchClient):
        def __init__(self) -> None:
            super().__init__(tmp_path)

        def fetch_text(self, url: str) -> str:
            return """
            Sennheiser Consumer Audio HD 650 - Audiophile Hi-Res Open Back Dynamic Headphone, Titan
            $5.00 shipping
            Sennheiser HD 650 Open Back Professional Headphone
            $471.11
            """

    intent = ParsedIntent(
        intent_type="search",
        raw_query="Find me the best deals for senheisser hd 650",
        category="electronics",
        filters={"brand": "Sennheiser", "product_family": "headphones", "model_number": "HD 650", "product_text": "Sennheiser HD 650 Headphones"},
    )
    adapter = GenericRetailLiveAdapter(
        name="newegg_live",
        retailer="Newegg",
        category="electronics",
        search_url_template="https://www.newegg.com/p/pl?d={query}",
        client=StubClient(),
        require_price=True,
    )
    offers = adapter.search(intent)
    assert len(offers) == 1
    assert offers[0].effective_price == 471.11


def test_extract_amazon_candidate_rejects_search_page_title_without_price() -> None:
    title, price = extract_amazon_candidate(
        """
        <title>Amazon.com : Find me the best deal on Sony WH-1000XM6</title>
        Search Amazon for Sony WH-1000XM6
        """,
        "Sony WH-1000XM6",
    )
    assert title is None
    assert price is None


def test_choose_best_lines_rejects_access_denied_pages() -> None:
    intent = ParsedIntent(
        intent_type="search",
        raw_query="Find me the best deals for senheisser hd 650 in marketplace mode",
        category="electronics",
        filters={"brand": "Sennheiser", "product_family": "headphones", "model_number": "HD 650", "product_text": "Sennheiser HD 650 Headphones", "source_mode": "trusted_plus_marketplace"},
    )
    text = """
    <html><body>
    <h1>Access Denied</h1>
    You don't have permission to access this server.
    https://errors.edgesuite.net/example
    </body></html>
    """
    assert choose_best_lines(text, intent) == []


def test_default_search_suppresses_marketplace_and_discovery_clutter() -> None:
    registry = SourceRegistry()
    intent = ParsedIntent(
        intent_type="search",
        raw_query="Find me the best deal on Sony WH-1000XM6",
        category="electronics",
        condition_preference="any",
        filters={"source_mode": "trusted_plus_discovery"},
    )
    offers = registry._filter_default_clutter([
        OfferCandidate(
            source_name="amazon_live",
            retailer="Amazon",
            listing_url="https://example.com/a",
            title="Sony WH-1000XM6",
            effective_price=399.0,
            condition="new",
            metadata={"lane": "trusted_retail"},
            source_role="truth",
        ),
        OfferCandidate(
            source_name="slickdeals_live",
            retailer="Slickdeals",
            listing_url="https://example.com/sd",
            title="Sony WH-1000XM6 deal thread",
            effective_price=389.0,
            condition="new",
            metadata={"lane": "discovery"},
            source_role="discovery",
        ),
        OfferCandidate(
            source_name="ebay_live",
            retailer="eBay",
            listing_url="https://example.com/e",
            title="Sony WH-1000XM6 used",
            effective_price=279.0,
            condition="used",
            metadata={"lane": "marketplace"},
            source_role="marketplace",
        ),
    ], intent)
    assert [offer.retailer for offer in offers] == ["Amazon"]


def test_bestbuy_candidate_prefers_product_line_over_retailer_search_copy() -> None:
    from app.sources.bestbuy_live_adapter import extract_bestbuy_candidate

    title, price = extract_bestbuy_candidate(
        '''
        Best Buy search results for Sony WH-1000XM6
        Sony WH-1000XM6 Wireless Noise Canceling Headphones
        $399.99
        ''',
        "Sony WH-1000XM6",
    )
    assert title == "Sony WH-1000XM6 Wireless Noise Canceling Headphones"
    assert price == 399.99


def test_ranker_downranks_unknown_price_and_generic_results() -> None:
    exact = OfferCandidate(
        source_name="walmart_live",
        retailer="Walmart",
        listing_url="https://example.com/walmart",
        title="Sony WH-1000XM6 Wireless Noise Canceling Headphones",
        effective_price=398.0,
        condition="new",
        metadata={"lane": "trusted_retail", "match_score": 0.98, "exact_model_match": True},
        source_role="truth",
        verification_state="unverified",
    )
    generic = OfferCandidate(
        source_name="target_live",
        retailer="Target",
        listing_url="https://example.com/target",
        title='"Find me the best deal on Sony WH-1000XM6" : Target',
        effective_price=None,
        condition="new",
        metadata={"lane": "trusted_retail", "match_score": 0.99, "generic_result": True},
        source_role="truth",
        verification_state="unverified",
    )
    ranked = Ranker().rank([generic, exact])
    assert ranked[0].offer.retailer == "Walmart"


def test_format_result_shows_lane_summary_when_present() -> None:
    text = format_result(
        {
            "intent_type": "search",
            "message": "Results:",
            "lane_summary": {
                "cheapest_trusted_retail": {
                    "title": "Sennheiser HD 650",
                    "retailer": "Newegg",
                    "effective_price": 471.11,
                },
                "cheapest_marketplace": {
                    "title": "Sennheiser HD 650 used",
                    "retailer": "eBay",
                    "effective_price": 299.0,
                },
                "best_overall_value": {
                    "title": "Sennheiser HD 650 used",
                    "retailer": "eBay",
                    "effective_price": 299.0,
                },
            },
            "results": [],
        }
    )
    assert "Trusted retail best: Sennheiser HD 650 — Newegg — $471.11" in text
    assert "Marketplace best: Sennheiser HD 650 used — eBay — $299.0" in text
    assert "Best overall value: Sennheiser HD 650 used — eBay — $299.0" in text


def test_registry_adds_enrichment_placeholders() -> None:
    registry = SourceRegistry()
    enriched = registry._apply_enrichment_placeholders([
        OfferCandidate(
            source_name="amazon_live",
            retailer="Amazon",
            listing_url="https://example.com",
            title="Sony WH-1000XM6",
            effective_price=299.99,
            metadata={},
        )
    ])
    enrichment = enriched[0].metadata.get("enrichment")
    assert enrichment["price_history"]["status"] == "not_connected"
    assert enrichment["coupon"]["applied"] is False


def test_frame_tv_match_beats_generic_samsung_noise() -> None:
    intent = ParsedIntent(
        intent_type="search",
        raw_query="Find me the best deal on Samsung The Frame TV 55 inch",
        category="electronics",
        filters={"brand": "Samsung", "product_family": "the frame tv", "product_text": "Samsung The Frame Tv", "size": "55 inch"},
    )
    frame_score = title_match_score("Samsung The Frame 55\" Class QLED 4K UHD Smart Tizen TV", intent)
    smaller_score = title_match_score("Samsung The Frame 43\" Class QLED 4K UHD Smart Tizen TV", intent)
    dvd_score = title_match_score("SAMSUNG USB 2.0 (3.0 Compatible) External DVD Burner Model SE-218GN/RSBD", intent)
    phone_score = title_match_score("Samsung Galaxy S21 Ultra 5G 128GB 12GB RAM (Unlocked) Phantom Silver", intent)
    assert frame_score > smaller_score
    assert frame_score > dvd_score
    assert frame_score > phone_score
    assert frame_score >= 0.7
    assert smaller_score < frame_score
    assert dvd_score < 0.3
    assert phone_score < 0.3


def test_ebay_marketplace_adapter_extracts_live_candidates(tmp_path) -> None:
    from app.sources.ebay_adapter import EbayMarketplaceAdapter

    class StubClient(LiveFetchClient):
        def __init__(self) -> None:
            super().__init__(tmp_path)

        def fetch_text(self, url: str) -> str:
            return """
            Sennheiser HD 650 Open-Back Audiophile Headphones - Used
            $249.99
            Sennheiser HD 650 Headphones Brand New
            $349.99
            Random replacement cable for Sennheiser HD 650
            $19.99
            """

    intent = ParsedIntent(
        intent_type="search",
        raw_query="Find me the best deals for senheisser hd 650 in marketplace mode",
        category="electronics",
        filters={"brand": "Sennheiser", "product_family": "headphones", "model_number": "HD 650", "product_text": "Sennheiser HD 650 Headphones", "source_mode": "trusted_plus_marketplace"},
    )
    offers = EbayMarketplaceAdapter(StubClient()).search(intent)
    assert len(offers) == 2
    assert offers[0].retailer == "eBay"
    assert offers[0].metadata["source_mode"] == "live_extract"
    assert all("replacement cable" not in offer.title.lower() for offer in offers)


def test_orchestrator_attaches_lane_summary() -> None:
    orchestrator = ShoppingOrchestrator(repository=None)  # type: ignore[arg-type]
    ranked = [
        RankedOffer(
            offer=OfferCandidate(
                source_name="newegg_live",
                retailer="Newegg",
                listing_url="https://example.com/n",
                title="Sennheiser HD 650",
                effective_price=471.11,
                condition="new",
                metadata={"lane": "trusted_retail"},
                verification_state="unverified",
            ),
            score=99.0,
        ),
        RankedOffer(
            offer=OfferCandidate(
                source_name="ebay_live",
                retailer="eBay",
                listing_url="https://example.com/e",
                title="Sennheiser HD 650 used",
                effective_price=299.0,
                condition="used",
                metadata={"lane": "marketplace"},
                verification_state="seller_unverified",
                source_role="marketplace",
            ),
            score=95.0,
        ),
    ]
    summary = orchestrator._attach_lane_summary(ranked, orchestrator._empty_budget_summary(ParsedIntent(intent_type="search", raw_query="q")))
    assert summary["lane_summary"]["cheapest_trusted_retail"]["retailer"] == "Newegg"
    assert summary["lane_summary"]["cheapest_marketplace"]["retailer"] == "eBay"
    assert summary["lane_summary"]["best_overall_value"]["retailer"] == "eBay"


def test_choose_best_lines_rejects_brand_store_noise_for_frame_tv() -> None:
    intent = ParsedIntent(
        intent_type="search",
        raw_query="Find me the best deal on Samsung The Frame TV 55 inch",
        category="electronics",
        filters={"brand": "Samsung", "product_family": "the frame tv", "product_text": "Samsung The Frame Tv", "size": "55 inch"},
    )
    text = """
    SAMSUNG - Tech & Security Solutions for Every Need
    Discover a wide range of Samsung products, from SSDs to monitors, tablets, and security solutions.
    Samsung The Frame 55\" Class QLED 4K UHD Smart Tizen TV
    $899.99
    Samsung Galaxy S21 Ultra 5G 128GB 12GB RAM (Unlocked) Phantom Silver
    $390.00
    SAMSUNG USB 2.0 (3.0 Compatible) External DVD Burner Model SE-218GN/RSBD
    $3.00
    """
    candidates = choose_best_lines(text, intent)
    assert [candidate[0] for candidate in candidates if "The Frame" in candidate[0]]
    assert all("Galaxy" not in candidate[0] for candidate in candidates)
    assert all("DVD Burner" not in candidate[0] for candidate in candidates)
    assert candidates[0][0] == 'Samsung The Frame 55" Class QLED 4K UHD Smart Tizen TV'
    assert candidates[0][1] == 899.99
