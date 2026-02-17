"""Local usage tracker — parses OpenClaw request logs for providers without billing APIs.

Reads log files from the configured log directory, extracts API usage entries,
and calculates monthly spend based on a hardcoded pricing table.
"""

from __future__ import annotations

import glob
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (USD)
PRICING = {
    # Anthropic
    "claude-opus-4": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "claude-haiku-3.5": {"input": 0.80, "output": 4.0},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "o1": {"input": 15.0, "output": 60.0},
    "o3-mini": {"input": 1.10, "output": 4.40},
    # Google
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
    # xAI
    "grok-3": {"input": 3.0, "output": 15.0},
    "grok-3-mini": {"input": 0.30, "output": 0.50},
}

# Map model prefixes to provider IDs
MODEL_PROVIDER_MAP = {
    "claude": "anthropic",
    "gpt": "openai",
    "o1": "openai",
    "o3": "openai",
    "gemini": "google",
    "grok": "xai",
}


def _get_provider_for_model(model: str) -> str | None:
    """Determine provider ID from model name."""
    model_lower = model.lower()
    for prefix, provider_id in MODEL_PROVIDER_MAP.items():
        if model_lower.startswith(prefix):
            return provider_id
    return None


def _get_pricing(model: str) -> dict | None:
    """Look up pricing for a model (exact match or prefix match)."""
    model_lower = model.lower()
    # Exact match
    if model_lower in PRICING:
        return PRICING[model_lower]
    # Prefix match (e.g., "gpt-4o-2024-01-01" matches "gpt-4o")
    for known_model, prices in PRICING.items():
        if model_lower.startswith(known_model):
            return prices
    return None


def _safe_int(value, default: int = 0) -> int:
    """Safely coerce a value to int."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default: float = 0.0) -> float:
    """Safely coerce a value to float."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _calculate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Calculate cost in USD for a single request."""
    pricing = _get_pricing(model)
    if pricing is None:
        return 0.0
    input_cost = (tokens_in / 1_000_000) * pricing["input"]
    output_cost = (tokens_out / 1_000_000) * pricing["output"]
    return input_cost + output_cost


class LocalTracker:
    """Parses local log files to track API usage for providers without billing APIs."""

    def __init__(self, log_dir: str):
        self.log_dir = os.path.expanduser(log_dir)

    def get_monthly_usage(self, provider_id: str) -> dict:
        """Get aggregated usage for the current month for a specific provider.

        Returns:
            dict with keys: spend, tokens_in, tokens_out
        """
        now = datetime.now(timezone.utc)
        current_month = now.month
        current_year = now.year

        total_spend = 0.0
        total_tokens_in = 0
        total_tokens_out = 0

        for entry in self._read_log_entries():
            if not isinstance(entry, dict):
                continue

            # Filter by month
            entry_time = entry.get("timestamp")
            if entry_time is None:
                continue

            try:
                if isinstance(entry_time, str):
                    dt = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
                elif isinstance(entry_time, (int, float)):
                    dt = datetime.fromtimestamp(entry_time, tz=timezone.utc)
                else:
                    continue
            except (ValueError, OSError, OverflowError):
                continue

            if dt.month != current_month or dt.year != current_year:
                continue

            # Filter by provider
            model = str(entry.get("model", ""))
            entry_provider = entry.get("provider", _get_provider_for_model(model))
            if entry_provider != provider_id:
                continue

            tokens_in = _safe_int(entry.get("input_tokens", entry.get("tokens_in", 0)))
            tokens_out = _safe_int(entry.get("output_tokens", entry.get("tokens_out", 0)))

            raw_cost = entry.get("cost")
            if raw_cost is not None:
                cost = _safe_float(raw_cost)
            else:
                cost = _calculate_cost(model, tokens_in, tokens_out)

            total_spend += cost
            total_tokens_in += tokens_in
            total_tokens_out += tokens_out

        return {
            "spend": round(total_spend, 4),
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
        }

    def _read_log_entries(self) -> list[dict]:
        """Read all log entries from the log directory.

        Expects JSON-lines (.jsonl) or JSON array (.json) log files.
        """
        entries = []
        if not os.path.isdir(self.log_dir):
            logger.debug("Log directory does not exist: %s", self.log_dir)
            return entries

        patterns = [
            os.path.join(self.log_dir, "*.jsonl"),
            os.path.join(self.log_dir, "*.json"),
            os.path.join(self.log_dir, "**", "*.jsonl"),
            os.path.join(self.log_dir, "**", "*.json"),
        ]

        seen_files = set()
        for pattern in patterns:
            for filepath in glob.glob(pattern, recursive=True):
                if filepath in seen_files:
                    continue
                seen_files.add(filepath)
                entries.extend(self._parse_log_file(filepath))

        return entries

    def _parse_log_file(self, filepath: str) -> list[dict]:
        """Parse a single log file (JSONL or JSON array)."""
        entries = []
        try:
            with open(filepath, "r") as f:
                content = f.read().strip()
                if not content:
                    return entries

                # Try JSONL first (one JSON object per line)
                if content.startswith("{"):
                    for line in content.split("\n"):
                        line = line.strip()
                        if line:
                            try:
                                entries.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                # Try JSON array
                elif content.startswith("["):
                    data = json.loads(content)
                    if isinstance(data, list):
                        entries.extend(data)
        except (OSError, json.JSONDecodeError) as e:
            logger.debug("Failed to parse log file %s: %s", filepath, e)

        return entries
