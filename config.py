"""Configuration management for AI Budget Dashboard.

Reads/writes settings from ~/.config/ai-budget/config.json.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

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
    "xaiTeamId": "",
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
    """Load configuration from disk, merging with defaults.

    Handles bad JSON gracefully by falling back to defaults.
    Auto-creates config file with defaults on first run.
    """
    path = config_path or get_config_path()
    config = _deep_copy_dict(DEFAULT_CONFIG)

    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                user_config = json.load(f)
            if isinstance(user_config, dict):
                config = _deep_merge(config, user_config)
            else:
                logger.warning("Config file is not a JSON object, using defaults.")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load config from %s: %s — using defaults.", path, e)
    else:
        # Auto-create config with defaults on first run
        try:
            save_config(config, path)
            logger.info("Created default config at %s", path)
        except OSError as e:
            logger.warning("Could not create default config: %s", e)

    return _validate_config(config)


def save_config(config: dict[str, Any], config_path: str | None = None) -> None:
    """Save configuration to disk."""
    path = config_path or get_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(config, f, indent=2)


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate and coerce config values to correct types/ranges."""
    # Validate refreshIntervalMinutes
    try:
        interval = int(config.get("refreshIntervalMinutes", 15))
    except (TypeError, ValueError):
        interval = 15
    config["refreshIntervalMinutes"] = max(1, min(interval, 1440))

    # Validate alertThresholds
    thresholds = config.get("alertThresholds", [80, 95])
    if not isinstance(thresholds, list):
        thresholds = [80, 95]
    validated_thresholds = []
    for t in thresholds:
        try:
            val = int(t)
            if 1 <= val <= 100:
                validated_thresholds.append(val)
        except (TypeError, ValueError):
            continue
    config["alertThresholds"] = validated_thresholds if validated_thresholds else [80, 95]

    # Validate displayMode
    if config.get("displayMode") not in ("compact", "icon"):
        config["displayMode"] = "compact"

    # Validate provider configs
    providers = config.get("providers", {})
    if not isinstance(providers, dict):
        config["providers"] = _deep_copy_dict(DEFAULT_CONFIG["providers"])
    else:
        for pid, pconf in providers.items():
            if not isinstance(pconf, dict):
                providers[pid] = {"budget": 0.0, "enabled": False}
                continue
            # Validate budget
            try:
                budget = float(pconf.get("budget", 0.0))
            except (TypeError, ValueError):
                budget = 0.0
            pconf["budget"] = max(0.0, budget)
            # Validate enabled
            pconf["enabled"] = bool(pconf.get("enabled", False))

    # Validate localTrackingLogPath
    log_path = config.get("localTrackingLogPath")
    if not isinstance(log_path, str) or not log_path.strip():
        config["localTrackingLogPath"] = "~/.openclaw/logs/"

    # Validate xaiTeamId
    xai_team_id = config.get("xaiTeamId")
    if not isinstance(xai_team_id, str):
        config["xaiTeamId"] = ""

    return config


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


def get_xai_team_id(config: dict[str, Any]) -> str:
    """Get the xAI team ID for Management API billing."""
    return config.get("xaiTeamId", "")


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
