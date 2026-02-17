"""macOS notifications for budget alerts.

Uses osascript (AppleScript) for reliable macOS notifications without
requiring additional dependencies or entitlements.
"""

from __future__ import annotations

import logging
import subprocess
import threading

logger = logging.getLogger(__name__)

# Track which alerts have been sent this month to avoid duplicates
_sent_alerts: set[str] = set()
_alerts_lock = threading.Lock()


def reset_alerts() -> None:
    """Reset sent alerts tracker (call on month rollover)."""
    with _alerts_lock:
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
        with _alerts_lock:
            already_sent = alert_key in _sent_alerts
        if usage_percent >= threshold and not already_sent:
            delivered = _send_notification(
                title="AI Budget Alert",
                message=f"{provider_name} has reached {usage_percent:.0f}% of budget ({threshold}% threshold).",
            )
            if delivered:
                with _alerts_lock:
                    _sent_alerts.add(alert_key)
            else:
                logger.warning(
                    "Notification for %s at %d%% failed; will retry next refresh.",
                    provider_id,
                    threshold,
                )


def _send_notification(title: str, message: str) -> bool:
    """Send a macOS notification via osascript.

    Returns True if the notification was delivered successfully, False otherwise.
    """
    script = (
        f'display notification "{_escape_applescript(message)}" '
        f'with title "{_escape_applescript(title)}"'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            logger.warning(
                "osascript failed (exit %d): %s", result.returncode, stderr
            )
            return False
        logger.info("Notification sent: %s — %s", title, message)
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("Failed to send notification: %s", e)
        return False


def _escape_applescript(text: str) -> str:
    """Escape special characters for AppleScript strings."""
    return text.replace("\\", "\\\\").replace('"', '\\"')
