"""macOS notifications for budget alerts.

Uses osascript (AppleScript) for reliable macOS notifications without
requiring additional dependencies or entitlements.
"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

# Track which alerts have been sent this month to avoid duplicates
_sent_alerts: set[str] = set()


def reset_alerts() -> None:
    """Reset sent alerts tracker (call on month rollover)."""
    _sent_alerts.clear()


def check_and_notify(
    provider_name: str,
    provider_id: str,
    usage_percent: float,
    thresholds: list[int],
) -> None:
    """Check if usage has crossed any threshold and send notification.

    Args:
        provider_name: Display name (e.g., "Anthropic").
        provider_id: Provider identifier (e.g., "anthropic").
        usage_percent: Current usage as percentage of budget (0-100).
        thresholds: List of threshold percentages to alert on (e.g., [80, 95]).
    """
    for threshold in sorted(thresholds):
        alert_key = f"{provider_id}_{threshold}"
        if usage_percent >= threshold and alert_key not in _sent_alerts:
            _send_notification(
                title="AI Budget Alert",
                message=f"{provider_name} has reached {usage_percent:.0f}% of budget ({threshold}% threshold).",
            )
            _sent_alerts.add(alert_key)


def _send_notification(title: str, message: str) -> None:
    """Send a macOS notification via osascript."""
    script = (
        f'display notification "{_escape_applescript(message)}" '
        f'with title "{_escape_applescript(title)}"'
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
        logger.info("Notification sent: %s — %s", title, message)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("Failed to send notification: %s", e)


def _escape_applescript(text: str) -> str:
    """Escape special characters for AppleScript strings."""
    return text.replace("\\", "\\\\").replace('"', '\\"')
