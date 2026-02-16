"""Google (Gemini) provider — local tracking fallback.

Google's Gemini API does not provide a billing/usage endpoint for API-key auth.
This provider falls back to parsing local OpenClaw logs to estimate usage.
"""

from __future__ import annotations

import logging

from providers.base import BaseProvider, UsageData

logger = logging.getLogger(__name__)


class GoogleProvider(BaseProvider):
    provider_id = "google"
    provider_name = "Google"

    def __init__(self, tracker=None):
        """Initialize with optional local tracker.

        Args:
            tracker: A LocalTracker instance for parsing usage logs.
        """
        self._tracker = tracker

    def fetch_usage(self, api_key: str | None, budget: float) -> UsageData:
        """Fetch usage from local tracking logs.

        Google doesn't have a simple billing API for API-key users,
        so we rely on local log parsing.
        """
        if self._tracker is None:
            logger.info("No local tracker for Google; returning zero usage.")
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                monthly_budget=budget,
            )

        try:
            tracked = self._tracker.get_monthly_usage("google")
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                current_spend=tracked["spend"],
                monthly_budget=budget,
                tokens_in=tracked["tokens_in"],
                tokens_out=tracked["tokens_out"],
            )
        except Exception as e:
            logger.error("Failed to get Google usage from local tracker: %s", e)
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                monthly_budget=budget,
            )
