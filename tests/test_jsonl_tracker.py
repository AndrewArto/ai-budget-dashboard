"""Tests for JSONL session tracker."""

import json
import os
import tempfile
from datetime import datetime, timezone

import pytest

from jsonl_tracker import JsonlTracker, _calculate_cost, _get_pricing


@pytest.fixture
def agents_dir(tmp_path):
    """Create a mock agents directory with JSONL session files."""
    sessions_dir = tmp_path / "opus" / "sessions"
    sessions_dir.mkdir(parents=True)
    return tmp_path


def _write_jsonl(agents_dir, agent="opus", filename="test.jsonl", entries=None):
    """Helper to write JSONL entries to a session file."""
    sessions_dir = agents_dir / agent / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    filepath = sessions_dir / filename
    with open(filepath, "w") as f:
        for entry in (entries or []):
            f.write(json.dumps(entry) + "\n")
    return filepath


def _make_message(
    provider="anthropic",
    model="claude-opus-4-6",
    input_tokens=100,
    output_tokens=50,
    cache_read=0,
    cache_write=0,
    cost_total=0,
    ts=None,
):
    """Create a JSONL message entry."""
    if ts is None:
        ts = datetime.now(timezone.utc).isoformat()
    return {
        "type": "message",
        "timestamp": ts,
        "message": {
            "role": "assistant",
            "provider": provider,
            "model": model,
            "usage": {
                "input": input_tokens,
                "output": output_tokens,
                "cacheRead": cache_read,
                "cacheWrite": cache_write,
                "totalTokens": input_tokens + output_tokens + cache_read + cache_write,
                "cost": {
                    "input": 0,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                    "total": cost_total,
                },
            },
        },
    }


class TestPricing:
    def test_exact_match(self):
        p = _get_pricing("claude-opus-4-6")
        assert p is not None
        assert p["input"] == 15.0
        assert p["output"] == 75.0

    def test_prefix_match(self):
        p = _get_pricing("gpt-4o-2024-01-01")
        assert p is not None
        assert p["input"] == 2.50

    def test_unknown_model(self):
        assert _get_pricing("unknown-model-xyz") is None

    def test_calculate_cost_basic(self):
        # 1M input tokens of claude-opus = $15
        cost = _calculate_cost("claude-opus-4-6", 1_000_000, 0)
        assert cost == pytest.approx(15.0, abs=0.01)

    def test_calculate_cost_with_cache(self):
        # 1M cache-read tokens at 10% of $15 = $1.50
        cost = _calculate_cost("claude-opus-4-6", 0, 0, cache_read=1_000_000)
        assert cost == pytest.approx(1.50, abs=0.01)

    def test_calculate_cost_unknown_model(self):
        assert _calculate_cost("unknown-model", 1000, 1000) == 0.0


class TestJsonlTracker:
    def test_empty_dir(self, agents_dir):
        tracker = JsonlTracker(str(agents_dir))
        result = tracker.get_monthly_usage("anthropic")
        assert result["spend"] == 0.0
        assert result["tokens_in"] == 0
        assert result["tokens_out"] == 0

    def test_single_entry(self, agents_dir):
        _write_jsonl(agents_dir, entries=[
            _make_message(input_tokens=1000, output_tokens=500),
        ])
        tracker = JsonlTracker(str(agents_dir))
        result = tracker.get_monthly_usage("anthropic")
        assert result["tokens_in"] == 1000
        assert result["tokens_out"] == 500
        assert result["spend"] > 0
        assert result["requests"] == 1

    def test_multiple_entries(self, agents_dir):
        _write_jsonl(agents_dir, entries=[
            _make_message(input_tokens=1000, output_tokens=500),
            _make_message(input_tokens=2000, output_tokens=1000),
        ])
        tracker = JsonlTracker(str(agents_dir))
        result = tracker.get_monthly_usage("anthropic")
        assert result["tokens_in"] == 3000
        assert result["tokens_out"] == 1500
        assert result["requests"] == 2

    def test_filter_by_provider(self, agents_dir):
        _write_jsonl(agents_dir, entries=[
            _make_message(provider="anthropic", input_tokens=1000, output_tokens=500),
            _make_message(provider="openai", model="gpt-4o", input_tokens=2000, output_tokens=1000),
        ])
        tracker = JsonlTracker(str(agents_dir))

        anthropic = tracker.get_monthly_usage("anthropic")
        assert anthropic["tokens_in"] == 1000
        assert anthropic["requests"] == 1

        openai = tracker.get_monthly_usage("openai")
        assert openai["tokens_in"] == 2000
        assert openai["requests"] == 1

    def test_filter_by_month(self, agents_dir):
        now = datetime.now(timezone.utc)
        old_ts = "2025-01-15T10:00:00Z"
        current_ts = now.isoformat()

        _write_jsonl(agents_dir, entries=[
            _make_message(input_tokens=1000, ts=old_ts),
            _make_message(input_tokens=2000, ts=current_ts),
        ])
        tracker = JsonlTracker(str(agents_dir))
        result = tracker.get_monthly_usage("anthropic")
        assert result["tokens_in"] == 2000
        assert result["requests"] == 1

    def test_use_cost_total_when_nonzero(self, agents_dir):
        _write_jsonl(agents_dir, entries=[
            _make_message(
                provider="openai",
                model="gpt-4o",
                input_tokens=1000,
                output_tokens=500,
                cost_total=0.05,
            ),
        ])
        tracker = JsonlTracker(str(agents_dir))
        result = tracker.get_monthly_usage("openai")
        assert result["spend"] == 0.05

    def test_cache_tokens_counted(self, agents_dir):
        _write_jsonl(agents_dir, entries=[
            _make_message(
                input_tokens=100,
                output_tokens=50,
                cache_read=10000,
                cache_write=500,
            ),
        ])
        tracker = JsonlTracker(str(agents_dir))
        result = tracker.get_monthly_usage("anthropic")
        # tokens_in should include input + cacheRead + cacheWrite
        assert result["tokens_in"] == 100 + 10000 + 500

    def test_get_all_providers(self, agents_dir):
        _write_jsonl(agents_dir, entries=[
            _make_message(provider="anthropic", input_tokens=1000, output_tokens=500),
            _make_message(provider="openai", model="gpt-4o", input_tokens=2000, output_tokens=1000),
            _make_message(provider="google", model="gemini-2.5-pro", input_tokens=500, output_tokens=200),
        ])
        tracker = JsonlTracker(str(agents_dir))
        results = tracker.get_all_providers_usage()
        assert results["anthropic"]["requests"] == 1
        assert results["openai"]["requests"] == 1
        assert results["google"]["requests"] == 1
        assert results["xai"]["requests"] == 0

    def test_multiple_agent_dirs(self, agents_dir):
        _write_jsonl(agents_dir, agent="opus", entries=[
            _make_message(input_tokens=1000, output_tokens=500),
        ])
        _write_jsonl(agents_dir, agent="sonnet", entries=[
            _make_message(input_tokens=2000, output_tokens=1000),
        ])
        tracker = JsonlTracker(str(agents_dir))
        result = tracker.get_monthly_usage("anthropic")
        assert result["tokens_in"] == 3000

    def test_malformed_lines_skipped(self, agents_dir):
        sessions_dir = agents_dir / "opus" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        filepath = sessions_dir / "test.jsonl"
        with open(filepath, "w") as f:
            f.write("not valid json\n")
            f.write(json.dumps(_make_message(input_tokens=1000, output_tokens=500)) + "\n")
            f.write("{\"type\": \"other\"}\n")

        tracker = JsonlTracker(str(agents_dir))
        result = tracker.get_monthly_usage("anthropic")
        assert result["tokens_in"] == 1000
        assert result["requests"] == 1

    def test_nonexistent_dir(self):
        tracker = JsonlTracker("/nonexistent/path")
        result = tracker.get_monthly_usage("anthropic")
        assert result["spend"] == 0.0

    def test_fallback_to_calculate_when_cost_total_missing(self, agents_dir):
        """When cost.total is absent/zero, fall back to _calculate_cost()."""
        entry = {
            "type": "message",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": {
                "provider": "anthropic",
                "model": "claude-opus-4-6",
                "usage": {
                    "input": 1_000_000,
                    "output": 0,
                    # No cost object at all
                },
            },
        }
        _write_jsonl(agents_dir, entries=[entry])
        tracker = JsonlTracker(str(agents_dir))
        result = tracker.get_monthly_usage("anthropic")
        # Should fall back: 1M input tokens of claude-opus-4-6 = $15
        assert result["spend"] == pytest.approx(15.0, abs=0.01)

    def test_fallback_when_cost_total_is_zero(self, agents_dir):
        """When cost.total is explicitly 0, fall back to _calculate_cost()."""
        entry = {
            "type": "message",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": {
                "provider": "anthropic",
                "model": "claude-opus-4-6",
                "usage": {
                    "input": 1_000_000,
                    "output": 0,
                    "cost": {"total": 0},
                },
            },
        }
        _write_jsonl(agents_dir, entries=[entry])
        tracker = JsonlTracker(str(agents_dir))
        result = tracker.get_monthly_usage("anthropic")
        assert result["spend"] == pytest.approx(15.0, abs=0.01)

    def test_cost_total_preferred_over_manual_calc(self, agents_dir):
        """cost.total takes precedence over manual token-based calculation."""
        # 1M input tokens of gpt-4o would be $2.50 manually, but cost.total=9.99 wins
        entry = {
            "type": "message",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": {
                "provider": "openai",
                "model": "gpt-4o",
                "usage": {
                    "input": 1_000_000,
                    "output": 0,
                    "cost": {"total": 9.99},
                },
            },
        }
        _write_jsonl(agents_dir, entries=[entry])
        tracker = JsonlTracker(str(agents_dir))
        result = tracker.get_monthly_usage("openai")
        assert result["spend"] == pytest.approx(9.99, abs=0.0001)


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


class TestJsonlTrackerWithRealFixture:
    """Tests using the real sample.jsonl fixture from tests/fixtures/."""

    @pytest.fixture
    def fixture_agents_dir(self, tmp_path):
        """Set up agents directory structure pointing at the real fixture file."""
        sessions_dir = tmp_path / "agent0" / "sessions"
        sessions_dir.mkdir(parents=True)
        fixture_src = os.path.join(FIXTURES_DIR, "sample.jsonl")
        import shutil
        shutil.copy(fixture_src, sessions_dir / "sample.jsonl")
        return tmp_path

    def test_fixture_loads_anthropic_entries(self, fixture_agents_dir):
        """sample.jsonl has 20 anthropic entries — all should be counted."""
        tracker = JsonlTracker(str(fixture_agents_dir))
        # Fixture entries are from 2026-02-01; force aggregate for that month
        result = tracker._aggregate("anthropic", 2026, 2)
        assert result["requests"] == 20

    def test_fixture_cost_total_used_not_manual_calc(self, fixture_agents_dir):
        """Spend should come from cost.total fields, not manual token pricing.

        The fixture uses claude-opus-4-5 (priced as $3/$15 per 1M tokens).
        Manual calc would give a different (lower) result than the pre-computed
        cost.total values that reflect the actual cache-heavy pricing.
        """
        tracker = JsonlTracker(str(fixture_agents_dir))
        result = tracker._aggregate("anthropic", 2026, 2)

        # Verify cost.total was used: sum all cost.total from fixture
        # (these values are pre-computed by OpenClaw and include cache pricing)
        assert result["spend"] > 0.0

        # Manual calc using token counts would undercount because the fixture
        # entries have heavy cache usage that cost.total captures correctly.
        # Verify spend is close to the sum of cost.total values (~0.2525 USD).
        assert result["spend"] == pytest.approx(0.2525, abs=0.001)

    def test_fixture_anthropic_spend_nonzero(self, fixture_agents_dir):
        """Anthropic spend from fixture is non-zero (not excluded as subscription)."""
        tracker = JsonlTracker(str(fixture_agents_dir))
        result = tracker._aggregate("anthropic", 2026, 2)
        assert result["spend"] > 0.0

    def test_fixture_no_openai_entries(self, fixture_agents_dir):
        """Fixture contains only anthropic entries — openai spend should be 0."""
        tracker = JsonlTracker(str(fixture_agents_dir))
        result = tracker._aggregate("openai", 2026, 2)
        assert result["requests"] == 0
        assert result["spend"] == 0.0
