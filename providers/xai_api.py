"""xAI (Grok) provider — Management API billing with local tracking fallback.

Uses xAI Management API at https://management-api.x.ai for billing data
when a management key and team ID are available. Falls back to local log
parsing when management credentials are not configured.
"""

from __future__ import annotations

import logging

import requests

from providers.base import BaseProvider, UsageData

logger = logging.getLogger(__name__)

XAI_MANAGEMENT_API_BASE = "https://management-api.x.ai"


class XAIProvider(BaseProvider):
    provider_id = "xai"
    provider_name = "xAI"

    def __init__(self, tracker=None):
        """Initialize with optional local tracker.

        Args:
            tracker: A LocalTracker instance for parsing usage logs.
        """
        self._tracker = tracker

    def fetch_usage(self, api_key: str | None, budget: float) -> UsageData:
        """Fetch usage from xAI Management API, falling back to local tracking.

        If a management key is provided (via api_key), attempts to fetch
        billing data from the Management API. On failure or if no key,
        falls back to local log parsing.
        """
        # Try Management API first if we have a key
        if api_key:
            try:
                result = self._call_billing_api(api_key)
                if result is not None:
                    return UsageData(
                        provider_id=self.provider_id,
                        provider_name=self.provider_name,
                        current_spend=result["spend"],
                        monthly_budget=budget,
                        tokens_in=result["tokens_in"],
                        tokens_out=result["tokens_out"],
                    )
            except Exception as e:
                logger.warning("xAI Management API failed, falling back to local tracking: %s", e)

        # Fall back to local tracker
        if self._tracker is not None:
            try:
                tracked = self._tracker.get_monthly_usage("xai")
                return UsageData(
                    provider_id=self.provider_id,
                    provider_name=self.provider_name,
                    current_spend=tracked["spend"],
                    monthly_budget=budget,
                    tokens_in=tracked["tokens_in"],
                    tokens_out=tracked["tokens_out"],
                )
            except Exception as e:
                logger.error("Failed to get xAI usage from local tracker: %s", e)

        if not api_key and self._tracker is None:
            logger.info("No API key or local tracker for xAI; returning zero usage.")

        return UsageData(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            monthly_budget=budget,
        )

    def _call_billing_api(self, api_key: str) -> dict | None:
        """Call the xAI Management API for billing data.

        Tries the invoice preview endpoint first (current month spend).
        The api_key should be in format "team_id:management_key" or just
        a management key (team_id defaults to "default").

        Returns dict with spend/tokens_in/tokens_out or None on failure.
        """
        # Parse team_id:key format
        if ":" in api_key:
            team_id, mgmt_key = api_key.split(":", 1)
        else:
            return None  # Need team_id:key format for Management API

        headers = {
            "Authorization": f"Bearer {mgmt_key}",
        }

        # Try invoice preview (current month)
        url = f"{XAI_MANAGEMENT_API_BASE}/v1/billing/teams/{team_id}/postpaid/invoice/preview"
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Extract spend from invoice preview
        total_spend = 0.0
        if isinstance(data, dict):
            # Try common fields for invoice total
            total_spend = float(data.get("total", data.get("amount", data.get("total_amount", 0.0))))
            # If amount is in cents, convert
            if data.get("currency_unit") == "cents":
                total_spend /= 100.0

        return {
            "spend": round(total_spend, 4),
            "tokens_in": 0,
            "tokens_out": 0,
        }
