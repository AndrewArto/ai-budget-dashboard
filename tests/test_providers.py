"""Tests for provider modules."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from providers.base import BaseProvider, UsageData, _format_count
from providers.anthropic_api import AnthropicProvider
from providers.openai_api import OpenAIProvider
from providers.google_api import GoogleProvider
from providers.xai_api import XAIProvider


class TestUsageData:
    def test_remaining_budget(self):
        usage = UsageData("test", "Test", current_spend=30.0, monthly_budget=100.0)
        assert usage.remaining == 70.0

    def test_remaining_budget_overspend(self):
        usage = UsageData("test", "Test", current_spend=120.0, monthly_budget=100.0)
        assert usage.remaining == 0.0

    def test_usage_percent(self):
        usage = UsageData("test", "Test", current_spend=75.0, monthly_budget=100.0)
        assert usage.usage_percent == 75.0

    def test_usage_percent_zero_budget(self):
        usage = UsageData("test", "Test", current_spend=10.0, monthly_budget=0.0)
        assert usage.usage_percent == 0.0

    def test_usage_percent_over_100(self):
        usage = UsageData("test", "Test", current_spend=150.0, monthly_budget=100.0)
        assert usage.usage_percent == 100.0

    def test_format_spend(self):
        usage = UsageData("test", "Test", current_spend=47.23, monthly_budget=200.0)
        assert usage.format_spend() == "$47.23/$200"

    def test_format_tokens(self):
        usage = UsageData("test", "Test", tokens_in=1_200_000, tokens_out=380_000)
        assert usage.format_tokens() == "1.2M in / 380K out"

    def test_format_tokens_small(self):
        usage = UsageData("test", "Test", tokens_in=500, tokens_out=100)
        assert usage.format_tokens() == "500 in / 100 out"


class TestFormatCount:
    def test_millions(self):
        assert _format_count(1_200_000) == "1.2M"
        assert _format_count(2_500_000) == "2.5M"

    def test_thousands(self):
        assert _format_count(380_000) == "380K"
        assert _format_count(1_500) == "2K"

    def test_small(self):
        assert _format_count(999) == "999"
        assert _format_count(0) == "0"


class TestAnthropicProvider:
    def test_no_api_key(self):
        provider = AnthropicProvider()
        usage = provider.fetch_usage(None, 80.0)
        assert usage.provider_id == "anthropic"
        assert usage.current_spend == 0.0
        assert usage.monthly_budget == 80.0

    @patch("providers.anthropic_api.requests.get")
    def test_successful_fetch_list_format(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"spend": 10.5, "input_tokens": 500_000, "output_tokens": 100_000},
            {"spend": 15.2, "input_tokens": 700_000, "output_tokens": 200_000},
        ]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = AnthropicProvider()
        usage = provider.fetch_usage("test-key", 80.0)

        assert usage.current_spend == pytest.approx(25.7)
        assert usage.tokens_in == 1_200_000
        assert usage.tokens_out == 300_000
        assert usage.monthly_budget == 80.0

    @patch("providers.anthropic_api.requests.get")
    def test_successful_fetch_dict_format(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"spend": 5.0, "input_tokens": 200_000, "output_tokens": 50_000},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = AnthropicProvider()
        usage = provider.fetch_usage("test-key", 80.0)

        assert usage.current_spend == 5.0
        assert usage.tokens_in == 200_000

    @patch("providers.anthropic_api.requests.get")
    def test_api_error(self, mock_get):
        mock_get.side_effect = Exception("Connection error")

        provider = AnthropicProvider()
        usage = provider.fetch_usage("test-key", 80.0)

        assert usage.current_spend == 0.0
        assert usage.monthly_budget == 80.0


class TestOpenAIProvider:
    def test_no_api_key(self):
        provider = OpenAIProvider()
        usage = provider.fetch_usage(None, 60.0)
        assert usage.provider_id == "openai"
        assert usage.current_spend == 0.0
        assert usage.monthly_budget == 60.0

    @patch("providers.openai_api.requests.get")
    def test_successful_fetch(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {
                    "results": [
                        {
                            "amount": {"value": 8.50},
                            "input_tokens": 400_000,
                            "output_tokens": 100_000,
                        },
                        {
                            "amount": {"value": 3.80},
                            "input_tokens": 200_000,
                            "output_tokens": 50_000,
                        },
                    ]
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = OpenAIProvider()
        usage = provider.fetch_usage("test-key", 60.0)

        assert usage.current_spend == pytest.approx(12.30)
        assert usage.tokens_in == 600_000
        assert usage.tokens_out == 150_000

    @patch("providers.openai_api.requests.get")
    def test_api_error(self, mock_get):
        mock_get.side_effect = Exception("Timeout")

        provider = OpenAIProvider()
        usage = provider.fetch_usage("test-key", 60.0)

        assert usage.current_spend == 0.0


class TestGoogleProvider:
    def test_no_tracker(self):
        provider = GoogleProvider(tracker=None)
        usage = provider.fetch_usage(None, 30.0)
        assert usage.provider_id == "google"
        assert usage.current_spend == 0.0
        assert usage.monthly_budget == 30.0

    def test_with_tracker(self):
        mock_tracker = MagicMock()
        mock_tracker.get_monthly_usage.return_value = {
            "spend": 4.10,
            "tokens_in": 2_100_000,
            "tokens_out": 450_000,
        }

        provider = GoogleProvider(tracker=mock_tracker)
        usage = provider.fetch_usage(None, 30.0)

        assert usage.current_spend == 4.10
        assert usage.tokens_in == 2_100_000
        mock_tracker.get_monthly_usage.assert_called_once_with("google")

    def test_tracker_error(self):
        mock_tracker = MagicMock()
        mock_tracker.get_monthly_usage.side_effect = Exception("Parse error")

        provider = GoogleProvider(tracker=mock_tracker)
        usage = provider.fetch_usage(None, 30.0)

        assert usage.current_spend == 0.0


class TestXAIProvider:
    def test_no_tracker(self):
        provider = XAIProvider(tracker=None)
        usage = provider.fetch_usage(None, 30.0)
        assert usage.provider_id == "xai"
        assert usage.current_spend == 0.0

    def test_with_tracker(self):
        mock_tracker = MagicMock()
        mock_tracker.get_monthly_usage.return_value = {
            "spend": 2.43,
            "tokens_in": 500_000,
            "tokens_out": 120_000,
        }

        provider = XAIProvider(tracker=mock_tracker)
        usage = provider.fetch_usage(None, 30.0)

        assert usage.current_spend == 2.43
        assert usage.tokens_in == 500_000
        mock_tracker.get_monthly_usage.assert_called_once_with("xai")
