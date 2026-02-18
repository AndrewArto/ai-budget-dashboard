"""JSONL session tracker -- parses OpenClaw session JSONL files for usage data.

Reads session files from ~/.openclaw/agents/*/sessions/*.jsonl,
extracts API usage entries, and calculates monthly spend per provider.
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
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-opus-4": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-3.5": {"input": 0.80, "output": 4.0},
    "claude-haiku-3-5": {"input": 0.80, "output": 4.0},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.0, "output": 8.0},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "o1": {"input": 15.0, "output": 60.0},
    "o3": {"input": 10.0, "output": 40.0},
    "o3-mini": {"input": 1.10, "output": 4.40},
    "o4-mini": {"input": 1.10, "output": 4.40},
    "gpt-5.2-pro": {"input": 10.0, "output": 40.0},
    # Google
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-3-pro": {"input": 1.25, "output": 10.0},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
    # xAI
    "grok-3": {"input": 3.0, "output": 15.0},
    "grok-3-mini": {"input": 0.30, "output": 0.50},
    "grok-4": {"input": 3.0, "output": 15.0},
}

# Cache pricing multipliers (relative to input price)
CACHE_READ_MULTIPLIER = 0.10   # 10% of input price
CACHE_WRITE_MULTIPLIER = 1.25  # 125% of input price

# Provider mapping from JSONL provider field
PROVIDER_IDS = {"anthropic", "openai", "google", "xai"}


def _get_pricing(model: str) -> dict | None:
    """Look up pricing for a model (exact match or prefix match)."""
    model_lower = model.lower()
    if model_lower in PRICING:
        return PRICING[model_lower]
    for known_model, prices in PRICING.items():
        if model_lower.startswith(known_model):
            return prices
    return None


def _calculate_cost(
    model: str,
    tokens_in: int,
    tokens_out: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> float:
    """Calculate cost in USD for a single request."""
    pricing = _get_pricing(model)
    if pricing is None:
        return 0.0
    input_price = pricing["input"]
    output_price = pricing["output"]

    input_cost = (tokens_in / 1_000_000) * input_price
    output_cost = (tokens_out / 1_000_000) * output_price
    cache_read_cost = (cache_read / 1_000_000) * input_price * CACHE_READ_MULTIPLIER
    cache_write_cost = (cache_write / 1_000_000) * input_price * CACHE_WRITE_MULTIPLIER

    return input_cost + output_cost + cache_read_cost + cache_write_cost


class JsonlTracker:
    """Parses OpenClaw session JSONL files to track API usage per provider."""

    def __init__(self, agents_dir: str):
        """Initialize with path to OpenClaw agents directory.

        Args:
            agents_dir: Path to ~/.openclaw/agents (contains */sessions/*.jsonl)
        """
        self.agents_dir = os.path.expanduser(agents_dir)

    def get_monthly_usage(self, provider_id: str) -> dict:
        """Get aggregated usage for the current month for a specific provider.

        Returns:
            dict with keys: spend, tokens_in, tokens_out, requests
        """
        now = datetime.now(timezone.utc)
        return self._aggregate(provider_id, now.year, now.month)

    def get_all_providers_usage(self) -> dict[str, dict]:
        """Get usage for all providers in one pass (more efficient)."""
        now = datetime.now(timezone.utc)
        results: dict[str, dict] = {}
        for pid in PROVIDER_IDS:
            results[pid] = {"spend": 0.0, "tokens_in": 0, "tokens_out": 0, "requests": 0}

        for entry in self._iter_entries():
            ts, provider, model, usage = entry
            if provider not in results:
                continue
            if ts.year != now.year or ts.month != now.month:
                continue

            tokens_in = usage.get("input", 0)
            tokens_out = usage.get("output", 0)
            cache_read = usage.get("cacheRead", 0)
            cache_write = usage.get("cacheWrite", 0)

            cost_obj = usage.get("cost", {})
            cost_total = cost_obj.get("total", 0) if isinstance(cost_obj, dict) else 0

            if cost_total and cost_total > 0:
                cost = cost_total
            else:
                cost = _calculate_cost(model, tokens_in, tokens_out, cache_read, cache_write)

            r = results[provider]
            r["spend"] += cost
            r["tokens_in"] += tokens_in + cache_read + cache_write
            r["tokens_out"] += tokens_out
            r["requests"] += 1

        for r in results.values():
            r["spend"] = round(r["spend"], 4)

        return results

    def _aggregate(self, provider_id: str, year: int, month: int) -> dict:
        """Aggregate usage for a single provider/month."""
        total_spend = 0.0
        total_in = 0
        total_out = 0
        total_requests = 0

        for entry in self._iter_entries():
            ts, provider, model, usage = entry
            if provider != provider_id:
                continue
            if ts.year != year or ts.month != month:
                continue

            tokens_in = usage.get("input", 0)
            tokens_out = usage.get("output", 0)
            cache_read = usage.get("cacheRead", 0)
            cache_write = usage.get("cacheWrite", 0)

            cost_obj = usage.get("cost", {})
            cost_total = cost_obj.get("total", 0) if isinstance(cost_obj, dict) else 0

            if cost_total and cost_total > 0:
                cost = cost_total
            else:
                cost = _calculate_cost(model, tokens_in, tokens_out, cache_read, cache_write)

            total_spend += cost
            total_in += tokens_in + cache_read + cache_write
            total_out += tokens_out
            total_requests += 1

        return {
            "spend": round(total_spend, 4),
            "tokens_in": total_in,
            "tokens_out": total_out,
            "requests": total_requests,
        }

    def _iter_entries(self):
        """Yield (timestamp, provider, model, usage_dict) from all JSONL files."""
        pattern = os.path.join(self.agents_dir, "*", "sessions", "*.jsonl")
        for filepath in glob.glob(pattern):
            yield from self._parse_jsonl(filepath)

    def _parse_jsonl(self, filepath: str):
        """Parse a single JSONL file, yielding usage entries."""
        try:
            with open(filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if entry.get("type") != "message":
                        continue

                    msg = entry.get("message", {})
                    if not isinstance(msg, dict):
                        continue

                    usage = msg.get("usage")
                    if not usage or not isinstance(usage, dict):
                        continue

                    provider = msg.get("provider", "")
                    model = msg.get("model", "")
                    ts_str = entry.get("timestamp") or entry.get("ts") or ""

                    if not provider or not ts_str:
                        continue

                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        continue

                    yield (ts, provider, model, usage)

        except OSError as e:
            logger.debug("Failed to read JSONL file %s: %s", filepath, e)
