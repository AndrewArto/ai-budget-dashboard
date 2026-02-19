"""Tests for provider implementations (all use JSONL tracker)."""

from unittest.mock import MagicMock

import pytest

from providers.anthropic_api import AnthropicProvider
from providers.openai_api import OpenAIProvider
from providers.google_api import GoogleProvider
from providers.xai_api import XAIProvider


def _make_tracker_mock(spend=1.50, tokens_in=10000, tokens_out=5000, requests=3):
    """Create a mock JSONL tracker."""
    tracker = MagicMock()
    tracker.get_monthly_usage.return_value = {
        "spend": spend,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "requests": requests,
    }
    return tracker


class TestAnthropicProvider:
    def test_fetch_with_tracker(self):
        tracker = _make_tracker_mock(spend=2.50, tokens_in=20000, tokens_out=8000)
        provider = AnthropicProvider(tracker=tracker)
        usage = provider.fetch_usage(None, budget=100.0)

        assert usage.provider_id == "anthropic"
        assert usage.is_subscription is True
        assert usage.tokens_in == 20000
        assert usage.tokens_out == 8000
        assert usage.requests == 3
        assert "Max" in usage.subscription_label
        tracker.get_monthly_usage.assert_called_once_with("anthropic")

    def test_fetch_without_tracker(self):
        provider = AnthropicProvider(tracker=None)
        usage = provider.fetch_usage(None, budget=100.0)
        assert usage.is_subscription is True
        assert "Claude Max" in usage.subscription_label

    def test_format_spend_shows_subscription(self):
        tracker = _make_tracker_mock(spend=75.0)
        provider = AnthropicProvider(tracker=tracker)
        usage = provider.fetch_usage(None, budget=100.0)
        assert "Max" in usage.format_spend()
        assert "$" not in usage.format_spend()


class TestOpenAIProvider:
    def test_fetch_with_tracker(self):
        tracker = _make_tracker_mock(spend=5.00, tokens_in=50000, tokens_out=20000)
        provider = OpenAIProvider(tracker=tracker)
        usage = provider.fetch_usage(None, budget=60.0)

        assert usage.provider_id == "openai"
        assert usage.current_spend == 5.00
        assert usage.tokens_in == 50000
        tracker.get_monthly_usage.assert_called_once_with("openai")

    def test_fetch_without_tracker(self):
        provider = OpenAIProvider(tracker=None)
        usage = provider.fetch_usage(None, budget=60.0)
        assert usage.current_spend == 0.0


class TestGoogleProvider:
    def test_fetch_with_tracker(self):
        tracker = _make_tracker_mock(spend=0.50, tokens_in=100000, tokens_out=30000)
        provider = GoogleProvider(tracker=tracker)
        usage = provider.fetch_usage(None, budget=30.0)

        assert usage.provider_id == "google"
        assert usage.current_spend == 0.50
        tracker.get_monthly_usage.assert_called_once_with("google")

    def test_fetch_without_tracker(self):
        provider = GoogleProvider(tracker=None)
        usage = provider.fetch_usage(None, budget=30.0)
        assert usage.current_spend == 0.0


class TestXAIProvider:
    def test_fetch_with_tracker(self):
        tracker = _make_tracker_mock(spend=1.00, tokens_in=15000, tokens_out=7000)
        provider = XAIProvider(tracker=tracker)
        usage = provider.fetch_usage(None, budget=30.0)

        assert usage.provider_id == "xai"
        assert usage.current_spend == 1.00
        tracker.get_monthly_usage.assert_called_once_with("xai")

    def test_fetch_without_tracker(self):
        provider = XAIProvider(tracker=None)
        usage = provider.fetch_usage(None, budget=30.0)
        assert usage.current_spend == 0.0
