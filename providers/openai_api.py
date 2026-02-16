"""OpenAI provider — fetches usage via /v1/organization/costs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from providers.base import BaseProvider, UsageData

logger = logging.getLogger(__name__)

OPENAI_API_BASE = "https://api.openai.com"


class OpenAIProvider(BaseProvider):
    provider_id = "openai"
    provider_name = "OpenAI"

    def fetch_usage(self, api_key: str | None, budget: float) -> UsageData:
        """Fetch usage from OpenAI organization costs API."""
        if not api_key:
            logger.warning("No API key for OpenAI; returning zero usage.")
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                monthly_budget=budget,
            )

        now = datetime.now(timezone.utc)
        start_of_month = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
        end_ts = int(now.timestamp())

        try:
            usage_data = self._call_costs_api(api_key, start_of_month, end_ts)
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                current_spend=usage_data["spend"],
                monthly_budget=budget,
                tokens_in=usage_data["tokens_in"],
                tokens_out=usage_data["tokens_out"],
            )
        except Exception as e:
            logger.error("Failed to fetch OpenAI usage: %s", e)
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                monthly_budget=budget,
            )

    def _call_costs_api(
        self, api_key: str, start_ts: int, end_ts: int
    ) -> dict:
        """Call the OpenAI organization costs API."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        url = f"{OPENAI_API_BASE}/v1/organization/costs"
        params = {
            "start_time": start_ts,
            "end_time": end_ts,
        }

        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        total_spend = 0.0
        total_tokens_in = 0
        total_tokens_out = 0

        # Parse cost data — typically has daily/bucketed entries
        entries = data.get("data", [])
        if isinstance(entries, list):
            for entry in entries:
                # Each entry may have "results" with line items
                results = entry.get("results", [])
                if isinstance(results, list):
                    for result in results:
                        amount = result.get("amount", {})
                        total_spend += amount.get("value", 0.0)
                        tokens_in = result.get("input_tokens", 0)
                        tokens_out = result.get("output_tokens", 0)
                        total_tokens_in += tokens_in
                        total_tokens_out += tokens_out
                else:
                    total_spend += entry.get("cost", entry.get("amount", 0.0))

        return {
            "spend": total_spend,
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
        }
