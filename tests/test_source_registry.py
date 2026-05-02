from __future__ import annotations

from app.formatting import format_result
from app.models.types import OfferCandidate, ParsedIntent
from app.ranking.ranker import Ranker
from app.sources.registry import SourceRegistry
from app.sources.amazon_adapter import AmazonAdapter
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


def test_suppress_stub_offers_when_live_exists() -> None:
    live = OfferCandidate(
        source_name="amazon_live",
        retailer="Amazon",
        listing_url="https://example.com/live",
        title="Sony WH-1000XM6",
        effective_price=299.99,
        metadata={"source_mode": "live_extract", "lane": "trusted_retail"},
    )
    stub = OfferCandidate(
        source_name="amazon",
        retailer="Amazon",
        listing_url="https://example.com/stub",
        title="Sony WH-1000XM6 stub",
        effective_price=309.99,
        metadata={"source_mode": "fallback_stub"},
    )
    kept = suppress_stub_offers([live, stub])
    assert kept == [live]


def test_suppress_stub_offers_when_any_priced_live_retail_exists() -> None:
    live = OfferCandidate(
        source_name="newegg_live",
        retailer="Newegg",
        listing_url="https://example.com/live",
        title="Sony WH-1000XM6",
        effective_price=458.0,
        metadata={"source_mode": "live_extract", "lane": "trusted_retail"},
    )
    stub = OfferCandidate(
        source_name="amazon",
        retailer="Amazon",
        listing_url="https://example.com/stub",
        title="Sony WH-1000XM6 stub",
        effective_price=299.98,
        metadata={"source_mode": "fallback_stub", "lane": "trusted_retail"},
    )
    kept = suppress_stub_offers([live, stub])
    assert kept == [live]


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


def test_amazon_stub_uses_product_text_not_raw_query() -> None:
    intent = ParsedIntent(
        intent_type="search",
        raw_query="Find me the best deal on Sony WH-1000XM6",
        category="electronics",
        filters={"product_text": "Sony WH-1000XM6"},
        product_terms=["Find", "me", "the", "best", "deal", "on", "Sony", "WH-1000XM6"],
    )
    offer = AmazonAdapter().search(intent)[0]
    assert offer.title == "Sony WH-1000XM6 — Amazon candidate"


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


def test_ranker_downranks_fallback_stub_even_when_stub_is_cheaper() -> None:
    live = OfferCandidate(
        source_name="newegg_live",
        retailer="Newegg",
        listing_url="https://example.com/newegg",
        title="Sony WH-1000XM6 Wireless Noise Canceling Headphones",
        effective_price=458.0,
        condition="new",
        metadata={"lane": "trusted_retail", "match_score": 0.9, "exact_model_match": True, "source_mode": "live_extract"},
        source_role="truth",
        verification_state="unverified",
    )
    stub = OfferCandidate(
        source_name="amazon",
        retailer="Amazon",
        listing_url="https://example.com/amazon",
        title="Sony WH-1000XM6 - Amazon candidate",
        effective_price=299.98,
        condition="new",
        metadata={"lane": "trusted_retail", "match_score": 0.0, "source_mode": "fallback_stub", "price_is_placeholder": True},
        source_role="truth",
        verification_state="partially_verified",
    )
    ranked = Ranker().rank([stub, live])
    assert ranked[0].offer.retailer == "Newegg"
    assert ranked[1].label is None



def test_format_result_labels_fallback_stub_prices_honestly() -> None:
    text = format_result(
        {
            "intent_type": "search",
            "message": "Results:",
            "results": [
                {
                    "title": "Sony WH-1000XM6 - Amazon candidate",
                    "retailer": "Amazon",
                    "effective_price": 299.98,
                    "confidence": "medium",
                    "source_mode": "fallback_stub",
                    "lane": "trusted_retail",
                    "source_role": "truth",
                    "verification_state": "partially_verified",
                    "condition": "new",
                    "price_is_placeholder": True,
                    "pricing_note": "Demo placeholder price until live extraction succeeds",
                    "enrichment": {},
                }
            ],
        }
    )
    assert "[fallback demo]" in text
    assert "demo price $299.98" in text
    assert "Demo placeholder price until live extraction succeeds" in text


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
        filters={"brand": "Samsung", "product_family": "the frame tv", "product_text": "Samsung The Frame Tv"},
    )
    frame_score = title_match_score("Samsung The Frame 55\" Class QLED 4K UHD Smart Tizen TV", intent)
    dvd_score = title_match_score("SAMSUNG USB 2.0 (3.0 Compatible) External DVD Burner Model SE-218GN/RSBD", intent)
    phone_score = title_match_score("Samsung Galaxy S21 Ultra 5G 128GB 12GB RAM (Unlocked) Phantom Silver", intent)
    assert frame_score > dvd_score
    assert frame_score > phone_score
    assert frame_score >= 0.7
    assert dvd_score < 0.3
    assert phone_score < 0.3


def test_choose_best_lines_rejects_brand_store_noise_for_frame_tv() -> None:
    intent = ParsedIntent(
        intent_type="search",
        raw_query="Find me the best deal on Samsung The Frame TV 55 inch",
        category="electronics",
        filters={"brand": "Samsung", "product_family": "the frame tv", "product_text": "Samsung The Frame Tv"},
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
