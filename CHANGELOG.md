# Changelog

## 2026-02-23 #001 fix: use OpenClaw JSONL cost.total for Anthropic dollar spend

### Problem
- Anthropic showed as a subscription (no dollar amount), excluded from total.
- Total was ~$52 while actual spend (from OpenClaw /usage) was ~$332.
- JSONL files already contain `usage.cost.total` computed by OpenClaw for ALL
  providers including Anthropic — this was not being used for Anthropic.

### Changes

#### providers/anthropic_api.py
- **Removed** `is_subscription=True` — Anthropic now reports as pay-per-use.
- **Changed** `current_spend` to use `tracked["spend"]` from JSONL `cost.total`
  instead of a fixed EUR subscription price constant.
- **Kept** `subscription_label` to indicate Claude Max plan in the UI
  (shown as sub-item in menu instead of subscription spend line).
- Rate-limit snapshot support unchanged.

#### main.py
- Updated `_add_provider_menu_items()`: for non-subscription providers that have
  a `subscription_label`, show it as an info sub-item (e.g. "Claude Max • Session 42%")
  instead of the token counts line.
- `_get_totals()` now naturally includes Anthropic spend since `is_subscription=False`.

#### jsonl_tracker.py
- No changes needed — `cost.total` preference over manual calculation was already
  implemented in both `_aggregate()` and `get_all_providers_usage()`.

### Tests
- `tests/test_providers.py`: updated `TestAnthropicProvider` —
  - `test_fetch_with_tracker`: asserts `is_subscription=False`, `current_spend=2.50`
  - `test_fetch_without_tracker`: asserts `is_subscription=False`
  - Renamed `test_format_spend_shows_subscription` → `test_format_spend_shows_dollar_amount`
  - Added `test_subscription_label_contains_max`
  - Added `test_anthropic_spend_included_in_totals`
- `tests/test_main.py`: updated `test_get_totals` — Anthropic spend now included.
  Added `test_get_totals_excludes_true_subscriptions` for backward-compatibility
  of the `is_subscription=True` exclusion logic.

### Result
- Anthropic now shows actual dollar spend from JSONL cost data.
- Total spend includes Anthropic, matching OpenClaw /usage report.
- All 110 tests pass.
