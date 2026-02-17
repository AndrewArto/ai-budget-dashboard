"""Tests for provider modules."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

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

    def test_error_field_default_none(self):
        usage = UsageData("test", "Test")
        assert usage.error is None

    def test_error_field_set(self):
        usage = UsageData("test", "Test", error="Something went wrong")
        assert usage.error == "Something went wrong"


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
    def test_successful_fetch_cost_report(self, mock_get):
        """Test with correct cost_report schema: amount in cents."""
        # First call = cost_report, second call = usage_report
        cost_resp = MagicMock()
        cost_resp.json.return_value = {
            "data": [
                {
                    "starting_at": "2026-02-01T00:00:00Z",
                    "ending_at": "2026-02-02T00:00:00Z",
                    "results": [
                        {"amount": "1050", "currency": "USD", "token_type": "uncached_input_tokens"},
                        {"amount": "1520", "currency": "USD", "token_type": "output_tokens"},
                    ],
                }
            ],
            "has_more": False,
            "next_page": None,
        }
        cost_resp.raise_for_status = MagicMock()

        usage_resp = MagicMock()
        usage_resp.json.return_value = {
            "data": [
                {
                    "results": [
                        {
                            "uncached_input_tokens": 500_000,
                            "cache_read_input_tokens": 100_000,
                            "output_tokens": 200_000,
                            "cache_creation": {},
                        }
                    ]
                }
            ],
            "has_more": False,
            "next_page": None,
        }
        usage_resp.raise_for_status = MagicMock()

        mock_get.side_effect = [cost_resp, usage_resp]

        provider = AnthropicProvider()
        usage = provider.fetch_usage("test-key", 80.0)

        # 1050 cents + 1520 cents = 2570 cents = $25.70
        assert usage.current_spend == pytest.approx(25.70)
        assert usage.tokens_in == 600_000  # 500K + 100K
        assert usage.tokens_out == 200_000
        assert usage.monthly_budget == 80.0

    @patch("providers.anthropic_api.requests.get")
    def test_pagination_cost_report(self, mock_get):
        """Test pagination with has_more / next_page."""
        page1_resp = MagicMock()
        page1_resp.json.return_value = {
            "data": [
                {
                    "results": [{"amount": "500", "currency": "USD"}]
                }
            ],
            "has_more": True,
            "next_page": "page2_token",
        }
        page1_resp.raise_for_status = MagicMock()

        page2_resp = MagicMock()
        page2_resp.json.return_value = {
            "data": [
                {
                    "results": [{"amount": "300", "currency": "USD"}]
                }
            ],
            "has_more": False,
            "next_page": None,
        }
        page2_resp.raise_for_status = MagicMock()

        usage_resp = MagicMock()
        usage_resp.json.return_value = {
            "data": [],
            "has_more": False,
            "next_page": None,
        }
        usage_resp.raise_for_status = MagicMock()

        mock_get.side_effect = [page1_resp, page2_resp, usage_resp]

        provider = AnthropicProvider()
        usage = provider.fetch_usage("test-key", 80.0)

        # 500 + 300 cents = 800 cents = $8.00
        assert usage.current_spend == pytest.approx(8.0)

    @patch("providers.anthropic_api.requests.get")
    def test_api_error_raises(self, mock_get):
        """Cost API failure should raise so caller preserves last-known-good data."""
        mock_get.side_effect = Exception("Connection error")

        provider = AnthropicProvider()
        with pytest.raises(Exception, match="Connection error"):
            provider.fetch_usage("test-key", 80.0)

    @patch("providers.anthropic_api.requests.get")
    def test_usage_api_failure_still_returns_cost(self, mock_get):
        """If usage_report fails, cost data should still be returned."""
        cost_resp = MagicMock()
        cost_resp.json.return_value = {
            "data": [{"results": [{"amount": "1000"}]}],
            "has_more": False,
        }
        cost_resp.raise_for_status = MagicMock()

        # Usage API raises
        mock_get.side_effect = [cost_resp, Exception("usage API down")]

        provider = AnthropicProvider()
        usage = provider.fetch_usage("test-key", 80.0)

        assert usage.current_spend == pytest.approx(10.0)
        assert usage.tokens_in == 0  # No token data available
        assert usage.tokens_out == 0
        assert usage.error is not None
        assert "Token fetch failed" in usage.error


class TestOpenAIProvider:
    def test_no_api_key(self):
        provider = OpenAIProvider()
        usage = provider.fetch_usage(None, 60.0)
        assert usage.provider_id == "openai"
        assert usage.current_spend == 0.0
        assert usage.monthly_budget == 60.0

    @patch("providers.openai_api.requests.get")
    def test_successful_fetch_nested_amount(self, mock_get):
        """Test with correct schema: amount is nested object."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "object": "page",
            "data": [
                {
                    "object": "bucket",
                    "results": [
                        {
                            "object": "organization.costs.result",
                            "amount": {"value": 8.50, "currency": "usd"},
                        },
                        {
                            "object": "organization.costs.result",
                            "amount": {"value": 3.80, "currency": "usd"},
                        },
                    ]
                }
            ],
            "has_more": False,
            "next_page": None,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = OpenAIProvider()
        usage = provider.fetch_usage("test-key", 60.0)

        assert usage.current_spend == pytest.approx(12.30)
        # Costs API doesn't return tokens
        assert usage.tokens_in == 0
        assert usage.tokens_out == 0

    @patch("providers.openai_api.requests.get")
    def test_pagination(self, mock_get):
        """Test pagination across multiple pages."""
        page1_resp = MagicMock()
        page1_resp.json.return_value = {
            "data": [
                {"results": [{"amount": {"value": 5.0, "currency": "usd"}}]}
            ],
            "has_more": True,
            "next_page": "cursor_abc",
        }
        page1_resp.raise_for_status = MagicMock()

        page2_resp = MagicMock()
        page2_resp.json.return_value = {
            "data": [
                {"results": [{"amount": {"value": 3.0, "currency": "usd"}}]}
            ],
            "has_more": False,
            "next_page": None,
        }
        page2_resp.raise_for_status = MagicMock()

        mock_get.side_effect = [page1_resp, page2_resp]

        provider = OpenAIProvider()
        usage = provider.fetch_usage("test-key", 60.0)

        assert usage.current_spend == pytest.approx(8.0)

    @patch("providers.openai_api.requests.get")
    def test_amount_as_flat_number(self, mock_get):
        """Test graceful handling when amount is a flat number (not dict)."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"results": [{"amount": 5.25}]}
            ],
            "has_more": False,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = OpenAIProvider()
        usage = provider.fetch_usage("test-key", 60.0)

        assert usage.current_spend == pytest.approx(5.25)

    @patch("providers.openai_api.requests.get")
    def test_api_error_raises(self, mock_get):
        """API failure should raise so caller preserves last-known-good data."""
        mock_get.side_effect = Exception("Timeout")

        provider = OpenAIProvider()
        with pytest.raises(Exception, match="Timeout"):
            provider.fetch_usage("test-key", 60.0)


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

    def test_tracker_error_raises(self):
        """Tracker failure should raise so caller preserves last-known-good data."""
        mock_tracker = MagicMock()
        mock_tracker.get_monthly_usage.side_effect = Exception("Parse error")

        provider = GoogleProvider(tracker=mock_tracker)
        with pytest.raises(Exception, match="Parse error"):
            provider.fetch_usage(None, 30.0)


class TestXAIProvider:
    def test_no_tracker_no_key(self):
        provider = XAIProvider(tracker=None)
        usage = provider.fetch_usage(None, 30.0)
        assert usage.provider_id == "xai"
        assert usage.current_spend == 0.0

    def test_with_tracker_no_key(self):
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

    @patch("providers.xai_api.requests.get")
    def test_billing_api_with_team_id(self, mock_get):
        """Test Management API billing with team_id:key format."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "total": 15.50,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = XAIProvider(tracker=None)
        usage = provider.fetch_usage("team123:mgmt-key-abc", 30.0)

        assert usage.current_spend == pytest.approx(15.50)
        mock_get.assert_called_once()
        # Verify correct URL with team_id
        call_args = mock_get.call_args
        assert "team123" in call_args[1].get("url", call_args[0][0] if call_args[0] else "")

    def test_key_without_team_id_falls_back_to_tracker(self):
        """Key without team_id:key format should fall back to local tracker."""
        mock_tracker = MagicMock()
        mock_tracker.get_monthly_usage.return_value = {
            "spend": 1.0,
            "tokens_in": 100,
            "tokens_out": 50,
        }

        provider = XAIProvider(tracker=mock_tracker)
        usage = provider.fetch_usage("just-a-key-no-colon", 30.0)

        # Should fall back to local tracker since no team_id:key format
        assert usage.current_spend == 1.0
        mock_tracker.get_monthly_usage.assert_called_once_with("xai")

    @patch("providers.xai_api.requests.get")
    def test_billing_api_failure_falls_back_to_tracker(self, mock_get):
        """When Management API fails, should fall back to local tracker."""
        mock_get.side_effect = Exception("API error")

        mock_tracker = MagicMock()
        mock_tracker.get_monthly_usage.return_value = {
            "spend": 3.00,
            "tokens_in": 200_000,
            "tokens_out": 50_000,
        }

        provider = XAIProvider(tracker=mock_tracker)
        usage = provider.fetch_usage("team1:key1", 30.0)

        assert usage.current_spend == 3.00
        assert usage.error is not None
        assert "Billing API failed" in usage.error
        mock_tracker.get_monthly_usage.assert_called_once_with("xai")

    @patch("providers.xai_api.requests.get")
    def test_billing_api_failure_no_tracker_raises(self, mock_get):
        """When Management API fails and no tracker, should raise."""
        mock_get.side_effect = Exception("API error")

        provider = XAIProvider(tracker=None)
        with pytest.raises(Exception, match="API error"):
            provider.fetch_usage("team1:key1", 30.0)

    @patch("providers.xai_api.requests.get")
    def test_config_team_id_used(self, mock_get):
        """team_id from config should be used instead of key parsing."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"total": 10.0}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = XAIProvider(tracker=None, team_id="config-team")
        usage = provider.fetch_usage("plain-mgmt-key", 30.0)

        assert usage.current_spend == pytest.approx(10.0)
        call_url = mock_get.call_args[0][0]
        assert "config-team" in call_url

    @patch("providers.xai_api.requests.get")
    def test_config_team_id_strips_legacy_prefix(self, mock_get):
        """Config team_id should strip team_id prefix from legacy key format."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"total": 5.0}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = XAIProvider(tracker=None, team_id="config-team")
        usage = provider.fetch_usage("old-team:mgmt-key-123", 30.0)

        assert usage.current_spend == pytest.approx(5.0)
        # Should use config-team, not old-team
        call_url = mock_get.call_args[0][0]
        assert "config-team" in call_url
        # Auth header should use mgmt-key-123, not old-team:mgmt-key-123
        call_headers = mock_get.call_args[1]["headers"]
        assert call_headers["Authorization"] == "Bearer mgmt-key-123"

    @patch("providers.xai_api.requests.get")
    def test_billing_api_usage_tokens(self, mock_get):
        """Test parsing usage/token fields from billing response."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "total": 20.0,
            "usage": {
                "input_tokens": 1_000_000,
                "output_tokens": 250_000,
            },
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = XAIProvider(tracker=None)
        usage = provider.fetch_usage("team1:key1", 30.0)

        assert usage.current_spend == pytest.approx(20.0)
        assert usage.tokens_in == 1_000_000
        assert usage.tokens_out == 250_000

    @patch("providers.xai_api.requests.get")
    def test_billing_api_cents_unit(self, mock_get):
        """Test currency_unit=cents conversion."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "total": 1500,
            "currency_unit": "cents",
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = XAIProvider(tracker=None)
        usage = provider.fetch_usage("team1:key1", 30.0)

        assert usage.current_spend == pytest.approx(15.0)

    @patch("providers.xai_api.requests.get")
    def test_billing_api_line_items_fallback(self, mock_get):
        """Test line_items parsing when top-level total is zero."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "line_items": [
                {"amount": 5.0},
                {"amount": 3.50},
            ],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = XAIProvider(tracker=None)
        usage = provider.fetch_usage("team1:key1", 30.0)

        assert usage.current_spend == pytest.approx(8.50)
