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

    def __init__(self, tracker=None, team_id: str = ""):
        """Initialize with optional local tracker and team ID.

        Args:
            tracker: A LocalTracker instance for parsing usage logs.
            team_id: xAI team ID for Management API. Can also be set via
                     config ``xaiTeamId`` or embedded in api_key as
                     ``team_id:management_key`` (legacy format).
        """
        self._tracker = tracker
        self._team_id = team_id

    def fetch_usage(self, api_key: str | None, budget: float) -> UsageData:
        """Fetch usage from xAI Management API, falling back to local tracking.

        The team_id is resolved in order:
        1. ``self._team_id`` (from config ``xaiTeamId``)
        2. ``team_id:key`` format in api_key (legacy)

        Billing API failures fall back to local tracker.
        If the tracker also fails (or is unavailable), the exception
        propagates so the caller can preserve last-known-good data.
        """
        billing_error = None

        # Try Management API first if we have a key
        if api_key:
            team_id, mgmt_key = self._resolve_credentials(api_key)
            if team_id and mgmt_key:
                try:
                    result = self._call_billing_api(team_id, mgmt_key)
                    return UsageData(
                        provider_id=self.provider_id,
                        provider_name=self.provider_name,
                        current_spend=result["spend"],
                        monthly_budget=budget,
                        tokens_in=result["tokens_in"],
                        tokens_out=result["tokens_out"],
                    )
                except Exception as e:
                    billing_error = e
                    logger.warning(
                        "xAI Management API failed, falling back to local tracking: %s", e
                    )
            else:
                # Key exists but no team_id configured — can't use billing API
                billing_error = "no team_id configured, using local tracking"
                logger.info("xAI: %s", billing_error)

        # Fall back to local tracker — let errors propagate
        if self._tracker is not None:
            tracked = self._tracker.get_monthly_usage("xai")
            if isinstance(billing_error, Exception):
                error_msg = f"Billing API failed: {billing_error}"
            elif isinstance(billing_error, str):
                error_msg = billing_error
            else:
                error_msg = None
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                current_spend=tracked["spend"],
                monthly_budget=budget,
                tokens_in=tracked["tokens_in"],
                tokens_out=tracked["tokens_out"],
                error=error_msg,
            )

        # No tracker and billing failed — raise so caller preserves last-known-good
        if isinstance(billing_error, Exception):
            raise billing_error

        if not api_key:
            logger.info("No API key or local tracker for xAI; returning zero usage.")

        return UsageData(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            monthly_budget=budget,
        )

    def _resolve_credentials(self, api_key: str) -> tuple[str, str]:
        """Resolve team_id and management key.

        Priority:
        1. self._team_id (from config xaiTeamId) + api_key as mgmt key
        2. team_id:key format in api_key (legacy)
        3. (empty, empty) if neither works

        Returns:
            (team_id, management_key) tuple.
        """
        if self._team_id:
            # Config-based team_id takes priority
            mgmt_key = api_key
            # Strip team_id prefix if the key also has it
            if ":" in api_key:
                _, mgmt_key = api_key.split(":", 1)
            return self._team_id, mgmt_key

        if ":" in api_key:
            team_id, mgmt_key = api_key.split(":", 1)
            return team_id, mgmt_key

        return "", ""

    def _call_billing_api(self, team_id: str, mgmt_key: str) -> dict:
        """Call the xAI Management API for billing data.

        Tries the invoice preview endpoint for current month spend.

        Returns dict with spend/tokens_in/tokens_out.

        Raises on HTTP/network errors or unparseable responses so the
        caller can fall back to local tracking or preserve last-known-good.
        """
        headers = {
            "Authorization": f"Bearer {mgmt_key}",
        }

        # Try invoice preview (current month)
        url = f"{XAI_MANAGEMENT_API_BASE}/v1/billing/teams/{team_id}/postpaid/invoice/preview"
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, dict):
            raise ValueError(
                f"xAI billing API returned non-dict response: {type(data).__name__}"
            )

        # Extract spend — handle total, amount, total_amount, subtotal
        total_spend = 0.0
        spend_found = False
        for spend_field in ("total", "amount", "total_amount", "subtotal"):
            val = data.get(spend_field)
            if val is not None:
                try:
                    total_spend = float(val)
                    spend_found = True
                except (TypeError, ValueError):
                    continue
                break

        # Handle cents vs dollars
        if data.get("currency_unit") == "cents" or data.get("unit") == "cents":
            total_spend /= 100.0

        # Extract token counts if available
        tokens_in = 0
        tokens_out = 0
        usage = data.get("usage", {})
        if isinstance(usage, dict):
            tokens_in = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)))
            tokens_out = int(usage.get("output_tokens", usage.get("completion_tokens", 0)))

        # Extract line items for detailed breakdown (if present)
        line_items = data.get("line_items", data.get("items", []))
        if isinstance(line_items, list) and line_items and total_spend == 0.0:
            for item in line_items:
                if isinstance(item, dict):
                    item_amount = item.get("amount", item.get("total", 0))
                    try:
                        total_spend += float(item_amount)
                        spend_found = True
                    except (TypeError, ValueError):
                        continue

        if not spend_found:
            raise ValueError(
                f"xAI billing API response has no parseable spend fields: {list(data.keys())}"
            )

        return {
            "spend": round(total_spend, 4),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
