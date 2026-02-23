"""Anthropic provider -- reads usage from OpenClaw session JSONL files.

For Claude Max (subscription/OAuth) users there is no billing API.
Shows as subscription (fixed €150/mo) with token counts and request count.
Rate-limit data shown when available.
"""

from __future__ import annotations

import json
import logging
import os

from providers.base import BaseProvider, UsageData, _format_count

logger = logging.getLogger(__name__)

RATELIMIT_SNAPSHOT_PATH = os.path.expanduser("~/.openclaw/state/anthropic-ratelimit.json")

# Claude Max plan price (EUR, monthly)
# Max = €150, Max 5x = €100 (Andrey downgrades to 5x on Mar 1, 2026)
CLAUDE_MAX_MONTHLY_EUR = 150.0
# Extra usage cap
EXTRA_USAGE_LIMIT_EUR = 100.0


class AnthropicProvider(BaseProvider):
    provider_id = "anthropic"
    provider_name = "Anthropic"

    def __init__(self, tracker=None):
        self._tracker = tracker

    def fetch_usage(self, api_key: str | None, budget: float) -> UsageData:
        """Fetch usage from local JSONL tracker.

        Returns subscription info (Claude Max €150/mo) with token counts.
        Dollar spend is NOT shown — Claude Max is a flat subscription,
        JSONL cost.total reflects API-equivalent pricing, not actual charges.
        """
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

        # Build subscription label
        label = f"Max \u2022 {_format_count(tracked['tokens_in'])} tok \u2022 {requests:,} req"

        # Try to read rate-limit snapshot for session/weekly limits
        ratelimit = self._read_ratelimit_snapshot()
        if ratelimit:
            headers = ratelimit.get("headers", {})
            remaining = headers.get("anthropic-ratelimit-unified-remaining")
            limit = headers.get("anthropic-ratelimit-unified-limit")
            if remaining is not None and limit is not None:
                try:
                    pct = round((1 - int(remaining) / int(limit)) * 100)
                    label = f"Max \u2022 Session {pct}%"
                except (ValueError, ZeroDivisionError):
                    pass

        return UsageData(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            current_spend=CLAUDE_MAX_MONTHLY_EUR,
            monthly_budget=CLAUDE_MAX_MONTHLY_EUR + EXTRA_USAGE_LIMIT_EUR,
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
