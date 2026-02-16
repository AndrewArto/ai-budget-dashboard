"""Anthropic provider — fetches usage via Admin API /v1/usage."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from providers.base import BaseProvider, UsageData

logger = logging.getLogger(__name__)

ANTHROPIC_API_BASE = "https://api.anthropic.com"


class AnthropicProvider(BaseProvider):
    provider_id = "anthropic"
    provider_name = "Anthropic"

    def fetch_usage(self, api_key: str | None, budget: float) -> UsageData:
        """Fetch usage from Anthropic Admin API."""
        if not api_key:
            logger.warning("No API key for Anthropic; returning zero usage.")
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                monthly_budget=budget,
            )

        now = datetime.now(timezone.utc)
        start_date = now.replace(day=1).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        try:
            usage_data = self._call_usage_api(api_key, start_date, end_date)
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                current_spend=usage_data["spend"],
                monthly_budget=budget,
                tokens_in=usage_data["tokens_in"],
                tokens_out=usage_data["tokens_out"],
            )
        except Exception as e:
            logger.error("Failed to fetch Anthropic usage: %s", e)
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                monthly_budget=budget,
            )

    def _call_usage_api(
        self, api_key: str, start_date: str, end_date: str
    ) -> dict:
        """Call the Anthropic Admin API for usage data."""
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        # The Admin API endpoint for usage
        url = f"{ANTHROPIC_API_BASE}/v1/usage"
        params = {
            "start_date": start_date,
            "end_date": end_date,
        }

        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        total_spend = 0.0
        total_tokens_in = 0
        total_tokens_out = 0

        # Parse the usage response — structure may vary;
        # handle both list-of-daily and summary formats
        if isinstance(data, list):
            for entry in data:
                total_spend += entry.get("spend", 0.0)
                total_tokens_in += entry.get("input_tokens", 0)
                total_tokens_out += entry.get("output_tokens", 0)
        elif isinstance(data, dict):
            # Could be paginated or summary
            entries = data.get("data", data.get("usage", []))
            if isinstance(entries, list):
                for entry in entries:
                    total_spend += entry.get("spend", 0.0)
                    total_tokens_in += entry.get("input_tokens", 0)
                    total_tokens_out += entry.get("output_tokens", 0)
            else:
                total_spend = data.get("total_spend", data.get("spend", 0.0))
                total_tokens_in = data.get("total_input_tokens", data.get("input_tokens", 0))
                total_tokens_out = data.get("total_output_tokens", data.get("output_tokens", 0))

        return {
            "spend": total_spend,
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
        }
