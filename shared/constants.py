"""
shared/constants.py

System-wide constants: Kafka topics, Redis key patterns, model names.
Centralizing these prevents magic strings from spreading across services.
"""

# ---------------------------------------------------------------------------
# Kafka topics
# ---------------------------------------------------------------------------

TOPIC_USER_EVENTS = "user-events"
TOPIC_FEATURE_UPDATES = "feature-updates"
TOPIC_MODEL_TRIGGERS = "model-triggers"

KAFKA_TOPICS = [TOPIC_USER_EVENTS, TOPIC_FEATURE_UPDATES, TOPIC_MODEL_TRIGGERS]

# ---------------------------------------------------------------------------
# Redis key patterns  (use .format(user_id=...) or f-strings)
# ---------------------------------------------------------------------------

REDIS_USER_RECENT_ITEMS = "user:{user_id}:recent_items"   # ZSET  — score = timestamp
REDIS_USER_EVENT_COUNTS = "user:{user_id}:event_counts"  # HASH  — event_type → count
REDIS_USER_RECS_CACHE   = "recs:{user_id}:k{k}"          # STRING — JSON, with TTL
REDIS_ITEM_POPULARITY   = "item:popularity"               # ZSET  — score = interaction count

REDIS_RECS_TTL_SECONDS = 300       # 5 minutes
REDIS_RECENT_ITEMS_MAX = 50        # keep last 50 interactions per user

# ---------------------------------------------------------------------------
# Model identifiers
# ---------------------------------------------------------------------------

MODEL_POPULARITY = "popularity"
MODEL_MATRIX_FACTORIZATION = "matrix_factorization"
MODEL_NEURAL_CF = "neural_cf"

MODEL_NAMES = [MODEL_POPULARITY, MODEL_MATRIX_FACTORIZATION, MODEL_NEURAL_CF]

# ---------------------------------------------------------------------------
# Event weights (used for scoring / feature engineering)
# ---------------------------------------------------------------------------

EVENT_WEIGHTS = {
    "product_view":     1.0,
    "search":           0.5,
    "add_to_cart":      3.0,
    "remove_from_cart": -1.0,
    "purchase":         5.0,
    "rating":           2.0,
}

# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

DEFAULT_K_VALUES = [5, 10, 20]
TRAIN_TEST_SPLIT_RATIO = 0.8
