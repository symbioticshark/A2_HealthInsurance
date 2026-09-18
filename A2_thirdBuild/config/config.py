"""
One BACKEND / MODEL / BASE_URL block, and exactly one function that knows a
vendor exists (call_model, in live_backend.py). Everything else in this
codebase is vendor-blind. Switching model is changing MODEL below (or
passing --model on the CLI) -- nothing else in loop.py/eval_harness.py
needs to change.

BACKEND="scripted" MUST be the default -- D5(a): a marker clones this repo
and runs it with no key and no network.
"""
import os

APP_VERSION = "3.0"

BACKEND = os.environ.get("A2_BACKEND", "scripted")   # "scripted" | "live"
MODEL = os.environ.get("A2_MODEL", "anthropic/claude-3-5-haiku")  # only used when BACKEND="live"
BASE_URL = os.environ.get("A2_BASE_URL", "https://openrouter.ai/api/v1")

# Shared network and model-output limits. Short control-plane requests use the
# short read timeout; paid model inference gets a longer response window.
HTTP_CONNECT_TIMEOUT_SECONDS = 15
HTTP_READ_TIMEOUT_SECONDS = 30
MODEL_READ_TIMEOUT_SECONDS = 180
MODEL_CATALOG_LIMIT = 1000
MODEL_MAX_OUTPUT_TOKENS = 1000
MODEL_OUTPUT_MAX_CHARS = 50_000
MODEL_JSON_MAX_CHARS = 20_000
ERROR_DETAIL_MAX_CHARS = 500

# D6's three price tiers (section 7 of the brief), USD per million tokens,
# (input, output). Used by cost_model.py -- kept alongside config so the
# whole vendor-neutral surface lives in one file.
PRICE_TABLE = {
    "cheap":    (0.10, 0.40),
    "mid":      (1.00, 5.00),
    "frontier": (5.00, 25.00),
}

# Reasoning cap applied on live runs (D6's "reasoning model pushes the bill
# up" section). Only meaningful when BACKEND="live" and MODEL is a
# reasoning-capable model. Our recommendation, per the brief: don't use a
# reasoning model for A2 -- this is here so the *option* is capped if a
# team member wants to compare it once, honestly, in the model battery.
REASONING = {"max_tokens": 1024}
