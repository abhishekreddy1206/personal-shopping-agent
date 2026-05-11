from app.parser.intent_parser import IntentParser


def test_watch_intent_detection() -> None:
    parser = IntentParser()
    intent = parser.parse("Track this monitor if it drops below $280")
    assert intent.intent_type == "watch_create"
    assert intent.category == "electronics"
    assert intent.target_price == 280.0


def test_history_intent_detection() -> None:
    parser = IntentParser()
    intent = parser.parse("Show my recent searches")
    assert intent.intent_type == "history_lookup"


def test_marketplace_mode_and_model_number_detection() -> None:
    parser = IntentParser()
    intake = parser.parse_structured("Search in marketplace mode for Sony WH-1000XM6 used")
    assert intake.parsed_intent.filters["source_mode"] == "trusted_plus_marketplace"
    assert intake.parsed_intent.filters["model_number"] == "WH-1000XM6"
    assert intake.product_intent.model_number == "WH-1000XM6"


def test_product_text_humanizes_terse_model_fragments() -> None:
    parser = IntentParser()
    intake = parser.parse_structured("Find me the best deal on Sony WH-1000XM6")
    assert intake.parsed_intent.filters["product_text"] == "Sony WH-1000XM6"



def test_watch_subject_and_label_keep_brand_and_model() -> None:
    parser = IntentParser()
    intake = parser.parse_structured("Track Sony WH-1000XM6 if it drops below $300")
    assert intake.watch_rule is not None
    assert intake.watch_rule.normalized_subject == "sony wh-1000xm6"
    assert intake.watch_rule.user_label == "Sony WH-1000XM6"


def test_frame_tv_family_detection() -> None:
    parser = IntentParser()
    intake = parser.parse_structured("Find me the best deal on Samsung The Frame TV 55 inch")
    assert intake.parsed_intent.category == "electronics"
    assert intake.parsed_intent.filters["brand"] == "Samsung"
    assert intake.parsed_intent.filters["product_family"] == "the frame tv"
    assert intake.parsed_intent.filters["product_text"] == "Samsung The Frame Tv"
    assert intake.parsed_intent.filters["size"] == "55 inch"
    assert intake.product_intent.size == "55 inch"


def test_sennheiser_hd650_misspelling_still_parses_as_electronics() -> None:
    parser = IntentParser()
    intake = parser.parse_structured("Find me the best deals for senheisser hd 650")
    assert intake.parsed_intent.category == "electronics"
    assert intake.parsed_intent.query_shape == "deal_hunt"
    assert intake.parsed_intent.filters["brand"] == "Sennheiser"
    assert intake.parsed_intent.filters["product_family"] == "headphones"
    assert intake.parsed_intent.filters["model_number"] == "HD 650"
    assert intake.parsed_intent.filters["product_text"] == "Sennheiser HD 650 Headphones"


def test_marketplace_mode_does_not_pollute_product_text() -> None:
    parser = IntentParser()
    intake = parser.parse_structured("Find me the best deals for senheisser hd 650 in marketplace mode")
    assert intake.parsed_intent.filters["source_mode"] == "trusted_plus_marketplace"
    assert intake.parsed_intent.filters["product_text"] == "Sennheiser HD 650 Headphones"


def test_conversational_deal_query_extracts_clean_bose_product() -> None:
    parser = IntentParser()
    intake = parser.parse_structured("Find me a good deal on bose quiet comfort ultra 2")
    assert intake.parsed_intent.category == "electronics"
    assert intake.parsed_intent.filters["brand"] == "Bose"
    assert intake.parsed_intent.filters["product_family"] == "headphones"
    assert intake.parsed_intent.filters["product_text"] == "Bose QuietComfort Ultra 2"


def test_bose_quietcomfort_ultra_2_without_type_requires_clarification() -> None:
    parser = IntentParser()
    intake = parser.parse_structured("Find me a good deal on Bose QuietComfort Ultra 2")
    assert intake.parsed_intent.needs_clarification is True
    assert intake.pending_clarification is not None
    assert intake.pending_clarification.kind == "product_type"
    assert intake.pending_clarification.options == ["over-ear headphones", "earbuds"]


def test_bose_quietcomfort_ultra_2_with_type_does_not_require_clarification() -> None:
    parser = IntentParser()
    intake = parser.parse_structured("Find me a good deal on Bose QuietComfort Ultra 2 headphones")
    assert intake.parsed_intent.needs_clarification is False
    assert intake.pending_clarification is None


def test_frame_tv_without_size_requires_clarification() -> None:
    parser = IntentParser()
    intake = parser.parse_structured("Find me the best deal on Samsung The Frame TV")
    assert intake.parsed_intent.needs_clarification is True
    assert intake.pending_clarification is not None
    assert intake.pending_clarification.kind == "size"
    assert intake.pending_clarification.expected_attribute == "size"


def test_frame_tv_with_size_preserves_existing_path() -> None:
    parser = IntentParser()
    intake = parser.parse_structured("Find me the best deal on Samsung The Frame TV 55 inch")
    assert intake.parsed_intent.needs_clarification is False
    assert intake.parsed_intent.filters["size"] == "55 inch"
