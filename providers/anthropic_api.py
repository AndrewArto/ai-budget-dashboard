"""Anthropic provider -- reads usage from OpenClaw session JSONL files.

For Claude Max (subscription/OAuth) users there is no billing API.
Shows token usage and request count instead of fake dollar amounts.
Rate-limit data shown when available (after openclaw/openclaw#20428).
"""

from __future__ import annotations

import json
import logging
import os

from providers.base import BaseProvider, UsageData, _format_count

logger = logging.getLogger(__name__)

RATELIMIT_SNAPSHOT_PATH = os.path.expanduser("~/.openclaw/state/anthropic-ratelimit.json")

# Monthly subscription price (for reference display only)
CLAUDE_MAX_MONTHLY = 100.0


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
                is_subscription=True,
                subscription_label="Claude Max",
            )

        tracked = self._tracker.get_monthly_usage("anthropic")
        requests = tracked.get("requests", 0)

        # Build subscription label with real usage info
        label = f"Max \u2022 {_format_count(tracked['tokens_in'])} tok \u2022 {requests:,} req"

        # Try to read rate-limit snapshot for extra context
        ratelimit = self._read_ratelimit_snapshot()
        if ratelimit:
            remaining = ratelimit.get("headers", {}).get(
                "anthropic-ratelimit-unified-remaining"
            )
            if remaining is not None:
                label = f"Max \u2022 {remaining} remaining"

        return UsageData(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            current_spend=CLAUDE_MAX_MONTHLY,
            monthly_budget=CLAUDE_MAX_MONTHLY,
            tokens_in=tracked["tokens_in"],
            tokens_out=tracked["tokens_out"],
            requests=requests,
            is_subscription=True,
            subscription_label=label,
        )

    @staticmethod
    def _read_ratelimit_snapshot() -> dict | None:
        """Read the Anthropic rate-limit snapshot if available."""
        try:
            with open(RATELIMIT_SNAPSHOT_PATH, "r") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
