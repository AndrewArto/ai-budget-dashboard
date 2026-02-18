"""Anthropic provider -- reads usage from OpenClaw session JSONL files.

For Claude Max (subscription/OAuth) users there is no billing API.
Cost is calculated from token counts using the pricing table.
"""

from __future__ import annotations

import json
import logging
import os

from providers.base import BaseProvider, UsageData

logger = logging.getLogger(__name__)

RATELIMIT_SNAPSHOT_PATH = os.path.expanduser("~/.openclaw/state/anthropic-ratelimit.json")


class AnthropicProvider(BaseProvider):
    provider_id = "anthropic"
    provider_name = "Anthropic"

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

        tracked = self._tracker.get_monthly_usage("anthropic")

        # Try to read rate-limit snapshot for extra context
        ratelimit = self._read_ratelimit_snapshot()
        error_msg = None
        if ratelimit:
            remaining = ratelimit.get("headers", {}).get(
                "anthropic-ratelimit-unified-remaining"
            )
            if remaining is not None:
                error_msg = f"Rate limit remaining: {remaining}"

        return UsageData(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            current_spend=tracked["spend"],
            monthly_budget=budget,
            tokens_in=tracked["tokens_in"],
            tokens_out=tracked["tokens_out"],
            error=error_msg,
        )

    @staticmethod
    def _read_ratelimit_snapshot() -> dict | None:
        """Read the Anthropic rate-limit snapshot if available."""
        try:
            with open(RATELIMIT_SNAPSHOT_PATH, "r") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
