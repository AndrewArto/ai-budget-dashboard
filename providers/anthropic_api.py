"""Anthropic provider — fetches cost data via Admin API /v1/organizations/cost_report."""

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
        """Fetch usage from Anthropic Admin API (cost_report + usage_report)."""
        if not api_key:
            logger.warning("No API key for Anthropic; returning zero usage.")
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                monthly_budget=budget,
            )

        now = datetime.now(timezone.utc)
        # RFC 3339 timestamps
        start_at = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        if now.month == 12:
            end_at = f"{now.year + 1}-01-01T00:00:00Z"
        else:
            end_at = f"{now.year}-{now.month + 1:02d}-01T00:00:00Z"

        try:
            cost_data = self._call_cost_api(api_key, start_at, end_at)
            # Supplement with token counts from usage_report
            tokens_in = 0
            tokens_out = 0
            try:
                usage_data = self._call_usage_api(api_key, start_at, end_at)
                tokens_in = usage_data["tokens_in"]
                tokens_out = usage_data["tokens_out"]
            except Exception as e:
                logger.warning("Failed to fetch Anthropic token counts: %s", e)

            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                current_spend=cost_data["spend"],
                monthly_budget=budget,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
        except Exception as e:
            logger.error("Failed to fetch Anthropic usage: %s", e)
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                monthly_budget=budget,
            )

    def _call_cost_api(
        self, api_key: str, start_at: str, end_at: str
    ) -> dict:
        """Call the Anthropic Admin cost_report API with pagination.

        The cost_report returns daily cost buckets. The amount field is
        in cents USD (string). Pagination via has_more / next_page.
        """
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

        url = f"{ANTHROPIC_API_BASE}/v1/organizations/cost_report"
        total_spend = 0.0
        page = None

        while True:
            params = {
                "starting_at": start_at,
                "ending_at": end_at,
                "bucket_width": "1d",
            }
            if page:
                params["page"] = page

            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for bucket in data.get("data", []):
                for result in bucket.get("results", []):
                    amount_cents = float(result.get("amount", 0))
                    total_spend += amount_cents / 100.0

            if not data.get("has_more", False):
                break
            next_page = data.get("next_page")
            if not next_page:
                break
            page = next_page

        return {"spend": round(total_spend, 4)}

    def _call_usage_api(
        self, api_key: str, start_at: str, end_at: str
    ) -> dict:
        """Call the Anthropic Admin usage_report API for token counts.

        Returns actual token counts (no dollar amounts).
        Pagination via has_more / next_page.
        """
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

        url = f"{ANTHROPIC_API_BASE}/v1/organizations/usage_report/messages"
        total_tokens_in = 0
        total_tokens_out = 0
        page = None

        while True:
            params = {
                "starting_at": start_at,
                "ending_at": end_at,
                "bucket_width": "1d",
            }
            if page:
                params["page"] = page

            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for bucket in data.get("data", []):
                for result in bucket.get("results", []):
                    total_tokens_in += result.get("uncached_input_tokens", 0)
                    total_tokens_in += result.get("cache_read_input_tokens", 0)
                    cache_creation = result.get("cache_creation", {})
                    if isinstance(cache_creation, dict):
                        total_tokens_in += cache_creation.get(
                            "ephemeral_5m_input_tokens", 0
                        )
                        total_tokens_in += cache_creation.get(
                            "ephemeral_1h_input_tokens", 0
                        )
                    total_tokens_out += result.get("output_tokens", 0)

            if not data.get("has_more", False):
                break
            next_page = data.get("next_page")
            if not next_page:
                break
            page = next_page

        return {
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
        }
