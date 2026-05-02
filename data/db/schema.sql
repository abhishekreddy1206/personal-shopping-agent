CREATE TABLE IF NOT EXISTS search_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  raw_query TEXT NOT NULL,
  intent_type TEXT NOT NULL,
  category TEXT,
  budget_min REAL,
  budget_max REAL,
  urgency TEXT,
  filters_json TEXT,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_queries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  raw_text TEXT NOT NULL,
  channel TEXT,
  surface TEXT,
  request_type TEXT NOT NULL,
  source_mode_requested TEXT,
  parse_status TEXT NOT NULL,
  parser_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parsed_intents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_query_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  intent_type TEXT NOT NULL,
  category TEXT,
  category_confidence REAL,
  query_shape TEXT,
  condition_preference TEXT,
  urgency TEXT,
  budget_min REAL,
  budget_max REAL,
  target_price REAL,
  product_terms_json TEXT,
  filters_json TEXT,
  FOREIGN KEY(user_query_id) REFERENCES user_queries(id)
);

CREATE TABLE IF NOT EXISTS product_intents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  parsed_intent_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  freeform_product_text TEXT NOT NULL,
  brand TEXT,
  product_family TEXT,
  model_number TEXT,
  variant TEXT,
  size TEXT,
  color TEXT,
  category TEXT,
  attributes_json TEXT,
  canonicalization_status TEXT,
  canonicalization_confidence REAL,
  FOREIGN KEY(parsed_intent_id) REFERENCES parsed_intents(id)
);

CREATE TABLE IF NOT EXISTS watch_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_intent_id INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  normalized_subject TEXT NOT NULL,
  user_label TEXT NOT NULL,
  target_price REAL,
  target_drop_percent REAL,
  condition_required TEXT,
  source_mode TEXT NOT NULL,
  preferred_sources_json TEXT,
  check_frequency TEXT NOT NULL,
  priority TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  notes TEXT,
  FOREIGN KEY(product_intent_id) REFERENCES product_intents(id)
);

CREATE TABLE IF NOT EXISTS evidence_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  source_name TEXT NOT NULL,
  storage_path TEXT,
  content_type TEXT,
  capture_method TEXT,
  sanitized INTEGER NOT NULL DEFAULT 1,
  retention_policy TEXT,
  content_hash TEXT
);

CREATE TABLE IF NOT EXISTS offer_evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_role TEXT NOT NULL,
  lane TEXT NOT NULL,
  retailer TEXT NOT NULL,
  seller_name TEXT,
  listing_url TEXT NOT NULL,
  title TEXT NOT NULL,
  condition TEXT,
  availability TEXT,
  base_price REAL,
  shipping_price REAL,
  tax_estimate REAL,
  effective_price REAL,
  currency TEXT DEFAULT 'USD',
  coupon_code TEXT,
  coupon_confidence REAL,
  seller_confidence REAL,
  extraction_confidence TEXT,
  verification_state TEXT NOT NULL,
  evidence_snapshot_id INTEGER,
  raw_extraction_notes TEXT,
  FOREIGN KEY(evidence_snapshot_id) REFERENCES evidence_snapshots(id)
);

CREATE TABLE IF NOT EXISTS search_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  search_request_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  canonical_query TEXT,
  summary_json TEXT,
  best_offer_id INTEGER,
  notes TEXT,
  FOREIGN KEY(search_request_id) REFERENCES search_requests(id)
);

CREATE TABLE IF NOT EXISTS canonical_products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category TEXT NOT NULL,
  brand TEXT,
  title TEXT NOT NULL,
  model_number TEXT,
  variant_json TEXT,
  attributes_json TEXT
);

CREATE TABLE IF NOT EXISTS offers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_product_id INTEGER,
  offer_evidence_id INTEGER,
  source_name TEXT NOT NULL,
  retailer TEXT NOT NULL,
  seller_name TEXT,
  listing_url TEXT NOT NULL,
  title TEXT NOT NULL,
  condition TEXT,
  availability TEXT,
  base_price REAL,
  shipping_price REAL,
  estimated_tax REAL,
  coupon_code TEXT,
  coupon_confidence REAL,
  effective_price REAL,
  currency TEXT DEFAULT 'USD',
  return_policy_summary TEXT,
  captured_at TEXT NOT NULL,
  raw_payload_path TEXT,
  FOREIGN KEY(canonical_product_id) REFERENCES canonical_products(id),
  FOREIGN KEY(offer_evidence_id) REFERENCES offer_evidence(id)
);

CREATE TABLE IF NOT EXISTS search_result_offers (
  search_result_id INTEGER NOT NULL,
  offer_id INTEGER NOT NULL,
  rank INTEGER NOT NULL,
  score REAL NOT NULL,
  label TEXT,
  reason_json TEXT,
  PRIMARY KEY(search_result_id, offer_id),
  FOREIGN KEY(search_result_id) REFERENCES search_results(id),
  FOREIGN KEY(offer_id) REFERENCES offers(id)
);

CREATE TABLE IF NOT EXISTS watch_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_product_id INTEGER,
  watch_rule_id INTEGER,
  created_at TEXT NOT NULL,
  user_label TEXT,
  normalized_subject TEXT,
  target_price REAL,
  target_drop_percent REAL,
  preferred_sources_json TEXT,
  check_frequency TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  notes TEXT,
  FOREIGN KEY(canonical_product_id) REFERENCES canonical_products(id),
  FOREIGN KEY(watch_rule_id) REFERENCES watch_rules(id)
);

CREATE TABLE IF NOT EXISTS price_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  watch_item_id INTEGER NOT NULL,
  offer_id INTEGER,
  observed_at TEXT NOT NULL,
  effective_price REAL,
  availability TEXT,
  trend_context_json TEXT,
  FOREIGN KEY(watch_item_id) REFERENCES watch_items(id),
  FOREIGN KEY(offer_id) REFERENCES offers(id)
);

CREATE TABLE IF NOT EXISTS alert_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  watch_item_id INTEGER NOT NULL,
  alert_type TEXT NOT NULL,
  old_price REAL,
  new_price REAL,
  message_text TEXT,
  triggered_at TEXT NOT NULL,
  delivered_at TEXT,
  dedupe_key TEXT,
  FOREIGN KEY(watch_item_id) REFERENCES watch_items(id)
);

CREATE TABLE IF NOT EXISTS feedback_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  signal_type TEXT NOT NULL,
  category TEXT,
  source_name TEXT,
  product_id INTEGER,
  watch_item_id INTEGER,
  value REAL,
  context_json TEXT
);

CREATE TABLE IF NOT EXISTS learned_preferences (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL,
  category TEXT,
  value_json TEXT,
  weight REAL NOT NULL,
  evidence_count INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_health (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_name TEXT NOT NULL,
  category TEXT,
  success_rate REAL,
  mismatch_rate REAL,
  stale_rate REAL,
  coupon_success_rate REAL,
  trust_score REAL,
  updated_at TEXT NOT NULL
);