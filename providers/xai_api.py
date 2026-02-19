"""xAI (Grok) provider -- JSONL tracker + optional billing API fallback."""

from __future__ import annotations

import logging

import requests

from providers.base import BaseProvider, UsageData

logger = logging.getLogger(__name__)

XAI_MANAGEMENT_API_BASE = "https://management-api.x.ai"
_REQUEST_TIMEOUT = 15


class XAIProvider(BaseProvider):
    provider_id = "xai"
    provider_name = "xAI"

    def __init__(self, tracker=None, team_id: str = "", mgmt_key: str = ""):
        self._tracker = tracker
        self._team_id = team_id
        self._mgmt_key = mgmt_key
        self._session = requests.Session()

    def fetch_usage(self, api_key: str | None, budget: float) -> UsageData:
        """Fetch usage: JSONL first, billing API fallback."""
        # Try JSONL first
        if self._tracker:
            tracked = self._tracker.get_monthly_usage("xai")
            if tracked["requests"] > 0:
                return UsageData(
                    provider_id=self.provider_id,
                    provider_name=self.provider_name,
                    current_spend=tracked["spend"],
                    monthly_budget=budget,
                    tokens_in=tracked["tokens_in"],
                    tokens_out=tracked["tokens_out"],
                    requests=tracked["requests"],
                )

        # Fallback: try Management API (needs management key, not API key)
        if self._team_id and self._mgmt_key:
            try:
                result = self._call_billing_api()
                return UsageData(
                    provider_id=self.provider_id,
                    provider_name=self.provider_name,
                    current_spend=result["spend"],
                    monthly_budget=budget,
                )
            except Exception as e:
                logger.warning("xAI billing API failed: %s", e)

        return UsageData(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            monthly_budget=budget,
        )

    def _call_billing_api(self) -> dict:
        """Call xAI Management API for billing data."""
        headers = {"Authorization": f"Bearer {self._mgmt_key}"}
        url = f"{XAI_MANAGEMENT_API_BASE}/v1/billing/teams/{self._team_id}/postpaid/invoice/preview"

        resp = self._session.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        total_spend = 0.0
        for field in ("total", "amount", "total_amount", "subtotal"):
            val = data.get(field)
            if val is not None:
                total_spend = float(val)
                break

        if data.get("currency_unit") == "cents" or data.get("unit") == "cents":
            total_spend /= 100.0

        return {"spend": round(total_spend, 4)}
