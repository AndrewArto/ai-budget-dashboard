"""OpenAI provider -- JSONL tracker + optional Costs API fallback.

Uses local JSONL data first. If no data found, tries the OpenAI
organization costs API (requires api.usage.read scope on the key).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import requests

from providers.base import BaseProvider, UsageData

logger = logging.getLogger(__name__)

OPENAI_API_BASE = "https://api.openai.com"
_REQUEST_TIMEOUT = 15


class OpenAIProvider(BaseProvider):
    provider_id = "openai"
    provider_name = "OpenAI"

    def __init__(self, tracker=None, admin_key: str | None = None):
        self._tracker = tracker
        self._admin_key = admin_key
        self._session = requests.Session()

    def fetch_usage(self, api_key: str | None, budget: float) -> UsageData:
        """Fetch usage: Costs API (admin key) first, JSONL fallback."""
        # Primary: Costs API with admin key
        costs_key = self._admin_key or api_key
        if costs_key:
            try:
                result = self._call_costs_api(costs_key)
                return UsageData(
                    provider_id=self.provider_id,
                    provider_name=self.provider_name,
                    current_spend=result["spend"],
                    monthly_budget=budget,
                    tokens_in=result["tokens_in"],
                    tokens_out=result["tokens_out"],
                )
            except Exception as e:
                logger.warning("OpenAI Costs API failed: %s", e)

        # Fallback: JSONL
        if self._tracker:
            tracked = self._tracker.get_monthly_usage("openai")
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

        return UsageData(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            monthly_budget=budget,
        )

    def _call_costs_api(self, api_key: str) -> dict:
        """Call OpenAI organization costs API."""
        now = datetime.now(timezone.utc)
        start_ts = int(
            now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
        )
        end_ts = int(now.timestamp())

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        url = f"{OPENAI_API_BASE}/v1/organization/costs"
        total_spend = 0.0
        page = None

        while True:
            params = {"start_time": start_ts, "end_time": end_ts, "limit": 180}
            if page:
                params["page"] = page

            resp = self._session.get(
                url, headers=headers, params=params, timeout=_REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()

            for bucket in data.get("data", []):
                for result in bucket.get("results", []):
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

        return {"spend": round(total_spend, 4), "tokens_in": 0, "tokens_out": 0}
