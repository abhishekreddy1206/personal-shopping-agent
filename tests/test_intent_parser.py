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
