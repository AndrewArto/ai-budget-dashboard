"""OpenAI provider — fetches cost data via /v1/organization/costs."""

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
        """Fetch usage from OpenAI organization costs API.

        Raises on API failure so the caller can preserve last-known-good data.
        """
        if not api_key:
            logger.warning("No API key for OpenAI; returning zero usage.")
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                monthly_budget=budget,
            )

        now = datetime.now(timezone.utc)
        start_of_month = int(
            now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
        )
        end_ts = int(now.timestamp())

        # Let API errors propagate — caller preserves last-known-good
        usage_data = self._call_costs_api(api_key, start_of_month, end_ts)
        return UsageData(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            current_spend=usage_data["spend"],
            monthly_budget=budget,
            tokens_in=usage_data["tokens_in"],
            tokens_out=usage_data["tokens_out"],
        )

    def _call_costs_api(
        self, api_key: str, start_ts: int, end_ts: int
    ) -> dict:
        """Call the OpenAI organization costs API with pagination.

        The amount field is a nested object: {"value": float, "currency": "usd"}.
        The Costs API does NOT return token counts — those come from the
        separate Usage API. Pagination via has_more / next_page.
        """
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        url = f"{OPENAI_API_BASE}/v1/organization/costs"
        total_spend = 0.0
        page = None

        while True:
            params = {
                "start_time": start_ts,
                "end_time": end_ts,
                "limit": 180,
            }
            if page:
                params["page"] = page

            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            buckets = data.get("data", [])
            for bucket in buckets:
                results = bucket.get("results", [])
                if isinstance(results, list):
                    for result in results:
                        amount = result.get("amount", {})
                        if isinstance(amount, dict):
                            total_spend += float(amount.get("value", 0.0))
                        elif isinstance(amount, (int, float)):
                            total_spend += float(amount)

            if not data.get("has_more", False):
                break
            next_page = data.get("next_page")
            if not next_page:
                break
            page = next_page

        return {
            "spend": round(total_spend, 4),
            "tokens_in": 0,
            "tokens_out": 0,
        }
