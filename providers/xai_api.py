"""xAI (Grok) provider -- reads usage from OpenClaw session JSONL files."""

from __future__ import annotations

import logging

from providers.base import BaseProvider, UsageData

logger = logging.getLogger(__name__)


class XAIProvider(BaseProvider):
    provider_id = "xai"
    provider_name = "xAI"

    def __init__(self, tracker=None):
        self._tracker = tracker

    def fetch_usage(self, api_key: str | None, budget: float) -> UsageData:
        """Fetch usage from local JSONL tracker."""
        if self._tracker is None:
            return UsageData(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                monthly_budget=budget,
            )

        tracked = self._tracker.get_monthly_usage("xai")
        return UsageData(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            current_spend=tracked["spend"],
            monthly_budget=budget,
            tokens_in=tracked["tokens_in"],
            tokens_out=tracked["tokens_out"],
        )
