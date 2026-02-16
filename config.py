"""Configuration management for AI Budget Dashboard.

Reads/writes settings from ~/.config/ai-budget/config.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_DIR = os.path.expanduser("~/.config/ai-budget")
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "providers": {
        "anthropic": {"budget": 80.0, "enabled": True},
        "openai": {"budget": 60.0, "enabled": True},
        "google": {"budget": 30.0, "enabled": True},
        "xai": {"budget": 30.0, "enabled": True},
    },
    "refreshIntervalMinutes": 15,
    "alertThresholds": [80, 95],
    "displayMode": "compact",
    "localTrackingLogPath": "~/.openclaw/logs/",
}

PROVIDER_DISPLAY_NAMES = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "google": "Google",
    "xai": "xAI",
}


def get_config_path() -> str:
    """Return the path to the config file."""
    return os.environ.get("AI_BUDGET_CONFIG_PATH", DEFAULT_CONFIG_PATH)


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load configuration from disk, merging with defaults."""
    path = config_path or get_config_path()
    config = _deep_copy_dict(DEFAULT_CONFIG)

    if os.path.exists(path):
        with open(path, "r") as f:
            user_config = json.load(f)
        config = _deep_merge(config, user_config)

    return config


def save_config(config: dict[str, Any], config_path: str | None = None) -> None:
    """Save configuration to disk."""
    path = config_path or get_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(config, f, indent=2)


def get_provider_budget(config: dict[str, Any], provider_id: str) -> float:
    """Get budget for a specific provider."""
    return config["providers"].get(provider_id, {}).get("budget", 0.0)


def is_provider_enabled(config: dict[str, Any], provider_id: str) -> bool:
    """Check if a provider is enabled."""
    return config["providers"].get(provider_id, {}).get("enabled", False)


def get_total_budget(config: dict[str, Any]) -> float:
    """Get sum of all enabled provider budgets."""
    total = 0.0
    for pid, pconf in config["providers"].items():
        if pconf.get("enabled", False):
            total += pconf.get("budget", 0.0)
    return total


def get_refresh_interval(config: dict[str, Any]) -> int:
    """Get refresh interval in minutes."""
    return config.get("refreshIntervalMinutes", 15)


def get_alert_thresholds(config: dict[str, Any]) -> list[int]:
    """Get alert threshold percentages."""
    return config.get("alertThresholds", [80, 95])


def get_log_path(config: dict[str, Any]) -> str:
    """Get the local tracking log path, expanded."""
    raw = config.get("localTrackingLogPath", "~/.openclaw/logs/")
    return os.path.expanduser(raw)


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _deep_copy_dict(d: dict) -> dict:
    """Simple deep copy for nested dicts/lists."""
    return json.loads(json.dumps(d))
