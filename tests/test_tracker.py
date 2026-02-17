"""Tests for the local usage tracker."""

import json
import os
import tempfile
from datetime import datetime, timezone

import pytest

from tracker import (
    LocalTracker,
    _calculate_cost,
    _get_provider_for_model,
    _get_pricing,
    _safe_int,
    _safe_float,
)


class TestModelMapping:
    def test_anthropic_models(self):
        assert _get_provider_for_model("claude-opus-4") == "anthropic"
        assert _get_provider_for_model("claude-sonnet-4") == "anthropic"
        assert _get_provider_for_model("claude-haiku-3.5") == "anthropic"

    def test_openai_models(self):
        assert _get_provider_for_model("gpt-4o") == "openai"
        assert _get_provider_for_model("gpt-4o-mini") == "openai"
        assert _get_provider_for_model("o1") == "openai"
        assert _get_provider_for_model("o3-mini") == "openai"

    def test_google_models(self):
        assert _get_provider_for_model("gemini-2.5-pro") == "google"
        assert _get_provider_for_model("gemini-2.0-flash") == "google"

    def test_xai_models(self):
        assert _get_provider_for_model("grok-3") == "xai"
        assert _get_provider_for_model("grok-3-mini") == "xai"

    def test_unknown_model(self):
        assert _get_provider_for_model("unknown-model") is None


class TestPricing:
    def test_exact_match(self):
        pricing = _get_pricing("gpt-4o")
        assert pricing is not None
        assert pricing["input"] == 2.50
        assert pricing["output"] == 10.0

    def test_prefix_match(self):
        pricing = _get_pricing("gpt-4o-2024-01-01")
        assert pricing is not None
        assert pricing["input"] == 2.50

    def test_unknown_model(self):
        assert _get_pricing("totally-unknown-model") is None


class TestSafeCoercion:
    def test_safe_int_valid(self):
        assert _safe_int(42) == 42
        assert _safe_int("100") == 100
        assert _safe_int(3.7) == 3

    def test_safe_int_invalid(self):
        assert _safe_int("not_a_number") == 0
        assert _safe_int(None) == 0
        assert _safe_int([1, 2]) == 0

    def test_safe_int_custom_default(self):
        assert _safe_int(None, default=-1) == -1

    def test_safe_float_valid(self):
        assert _safe_float(3.14) == pytest.approx(3.14)
        assert _safe_float("2.5") == pytest.approx(2.5)
        assert _safe_float(42) == 42.0

    def test_safe_float_invalid(self):
        assert _safe_float("not_a_number") == 0.0
        assert _safe_float(None) == 0.0
        assert _safe_float({"value": 1}) == 0.0


class TestCalculateCost:
    def test_known_model(self):
        # gpt-4o: $2.50/1M in, $10.0/1M out
        cost = _calculate_cost("gpt-4o", 1_000_000, 1_000_000)
        assert cost == pytest.approx(12.50)

    def test_partial_tokens(self):
        # 500K in, 200K out for gpt-4o
        cost = _calculate_cost("gpt-4o", 500_000, 200_000)
        expected = (500_000 / 1_000_000) * 2.50 + (200_000 / 1_000_000) * 10.0
        assert cost == pytest.approx(expected)

    def test_unknown_model_zero_cost(self):
        cost = _calculate_cost("unknown-model", 1_000_000, 1_000_000)
        assert cost == 0.0


class TestLocalTracker:
    @pytest.fixture
    def log_dir(self):
        with tempfile.TemporaryDirectory() as d:
            yield d

    def _write_jsonl(self, log_dir, filename, entries):
        filepath = os.path.join(log_dir, filename)
        with open(filepath, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def _write_json_array(self, log_dir, filename, entries):
        filepath = os.path.join(log_dir, filename)
        with open(filepath, "w") as f:
            json.dump(entries, f)

    def test_empty_log_dir(self, log_dir):
        tracker = LocalTracker(log_dir)
        result = tracker.get_monthly_usage("google")
        assert result["spend"] == 0.0
        assert result["tokens_in"] == 0
        assert result["tokens_out"] == 0

    def test_nonexistent_log_dir(self):
        tracker = LocalTracker("/nonexistent/path")
        result = tracker.get_monthly_usage("google")
        assert result["spend"] == 0.0

    def test_jsonl_parsing(self, log_dir):
        now = datetime.now(timezone.utc)
        entries = [
            {
                "timestamp": now.isoformat(),
                "model": "gemini-2.5-pro",
                "input_tokens": 1_000_000,
                "output_tokens": 200_000,
            },
            {
                "timestamp": now.isoformat(),
                "model": "gemini-2.0-flash",
                "input_tokens": 500_000,
                "output_tokens": 100_000,
            },
        ]
        self._write_jsonl(log_dir, "usage.jsonl", entries)

        tracker = LocalTracker(log_dir)
        result = tracker.get_monthly_usage("google")

        assert result["tokens_in"] == 1_500_000
        assert result["tokens_out"] == 300_000
        assert result["spend"] > 0

    def test_json_array_parsing(self, log_dir):
        now = datetime.now(timezone.utc)
        entries = [
            {
                "timestamp": now.isoformat(),
                "model": "grok-3",
                "input_tokens": 500_000,
                "output_tokens": 120_000,
            },
        ]
        self._write_json_array(log_dir, "usage.json", entries)

        tracker = LocalTracker(log_dir)
        result = tracker.get_monthly_usage("xai")

        assert result["tokens_in"] == 500_000
        assert result["tokens_out"] == 120_000

    def test_filters_by_provider(self, log_dir):
        now = datetime.now(timezone.utc)
        entries = [
            {
                "timestamp": now.isoformat(),
                "model": "gemini-2.5-pro",
                "input_tokens": 1_000_000,
                "output_tokens": 200_000,
            },
            {
                "timestamp": now.isoformat(),
                "model": "grok-3",
                "input_tokens": 500_000,
                "output_tokens": 100_000,
            },
        ]
        self._write_jsonl(log_dir, "usage.jsonl", entries)

        tracker = LocalTracker(log_dir)

        google_result = tracker.get_monthly_usage("google")
        assert google_result["tokens_in"] == 1_000_000

        xai_result = tracker.get_monthly_usage("xai")
        assert xai_result["tokens_in"] == 500_000

    def test_filters_by_month(self, log_dir):
        now = datetime.now(timezone.utc)
        # Current month entry
        entries = [
            {
                "timestamp": now.isoformat(),
                "model": "grok-3",
                "input_tokens": 500_000,
                "output_tokens": 100_000,
            },
            {
                # Last year — should be excluded
                "timestamp": "2025-01-15T10:00:00+00:00",
                "model": "grok-3",
                "input_tokens": 999_999,
                "output_tokens": 999_999,
            },
        ]
        self._write_jsonl(log_dir, "usage.jsonl", entries)

        tracker = LocalTracker(log_dir)
        result = tracker.get_monthly_usage("xai")

        assert result["tokens_in"] == 500_000

    def test_explicit_provider_field(self, log_dir):
        now = datetime.now(timezone.utc)
        entries = [
            {
                "timestamp": now.isoformat(),
                "provider": "google",
                "model": "some-custom-model",
                "input_tokens": 300_000,
                "output_tokens": 50_000,
                "cost": 1.25,
            },
        ]
        self._write_jsonl(log_dir, "usage.jsonl", entries)

        tracker = LocalTracker(log_dir)
        result = tracker.get_monthly_usage("google")

        assert result["tokens_in"] == 300_000
        assert result["spend"] == 1.25

    def test_cost_calculation(self, log_dir):
        now = datetime.now(timezone.utc)
        # gemini-2.5-pro: $1.25/1M in, $10.0/1M out
        entries = [
            {
                "timestamp": now.isoformat(),
                "model": "gemini-2.5-pro",
                "input_tokens": 2_000_000,
                "output_tokens": 400_000,
            },
        ]
        self._write_jsonl(log_dir, "usage.jsonl", entries)

        tracker = LocalTracker(log_dir)
        result = tracker.get_monthly_usage("google")

        # Expected: (2M/1M)*1.25 + (400K/1M)*10.0 = 2.50 + 4.00 = 6.50
        assert result["spend"] == pytest.approx(6.50)

    def test_string_token_values_coerced(self, log_dir):
        """Token values as strings should be coerced to int."""
        now = datetime.now(timezone.utc)
        entries = [
            {
                "timestamp": now.isoformat(),
                "model": "grok-3",
                "input_tokens": "500000",
                "output_tokens": "120000",
            },
        ]
        self._write_jsonl(log_dir, "usage.jsonl", entries)

        tracker = LocalTracker(log_dir)
        result = tracker.get_monthly_usage("xai")

        assert result["tokens_in"] == 500_000
        assert result["tokens_out"] == 120_000

    def test_malformed_token_values_default_to_zero(self, log_dir):
        """Non-numeric token values should default to 0."""
        now = datetime.now(timezone.utc)
        entries = [
            {
                "timestamp": now.isoformat(),
                "model": "grok-3",
                "input_tokens": "not_a_number",
                "output_tokens": None,
                "cost": 1.0,
            },
        ]
        self._write_jsonl(log_dir, "usage.jsonl", entries)

        tracker = LocalTracker(log_dir)
        result = tracker.get_monthly_usage("xai")

        assert result["tokens_in"] == 0
        assert result["tokens_out"] == 0
        assert result["spend"] == 1.0

    def test_string_cost_value_coerced(self, log_dir):
        """Cost as string should be coerced to float."""
        now = datetime.now(timezone.utc)
        entries = [
            {
                "timestamp": now.isoformat(),
                "provider": "xai",
                "model": "grok-3",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost": "2.50",
            },
        ]
        self._write_jsonl(log_dir, "usage.jsonl", entries)

        tracker = LocalTracker(log_dir)
        result = tracker.get_monthly_usage("xai")

        assert result["spend"] == pytest.approx(2.50)

    def test_non_dict_entries_skipped(self, log_dir):
        """Non-dict entries in log files should be silently skipped."""
        now = datetime.now(timezone.utc)
        filepath = os.path.join(log_dir, "usage.json")
        with open(filepath, "w") as f:
            json.dump(
                [
                    "not_a_dict",
                    42,
                    {
                        "timestamp": now.isoformat(),
                        "model": "grok-3",
                        "input_tokens": 100,
                        "output_tokens": 50,
                    },
                ],
                f,
            )

        tracker = LocalTracker(log_dir)
        result = tracker.get_monthly_usage("xai")

        assert result["tokens_in"] == 100
        assert result["tokens_out"] == 50
