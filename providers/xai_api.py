"""xAI (Grok) provider — local tracking fallback.

xAI does not yet have a dedicated billing API.
This provider falls back to parsing local OpenClaw logs to estimate usage.
"""

from __future__ import annotations

import logging

from providers.base import BaseProvider, UsageData

logger = logging.getLogger(__name__)


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
        """Fetch usage from local tracking logs.

        xAI doesn't have a billing API yet, so we rely on local log parsing.
        """
        if self._tracker is None:
            logger.info("No local tracker for xAI; returning zero usage.")
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                monthly_budget=budget,
            )

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
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                monthly_budget=budget,
            )
