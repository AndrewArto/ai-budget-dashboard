"""AI Budget Dashboard — macOS menu bar application.

Entry point for the rumps-based menu bar app that displays
AI API spending across providers.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

import rumps

from PyObjCTools import AppHelper

import config as app_config
import keychain
import notifier
from providers.base import UsageData
from providers.anthropic_api import AnthropicProvider
from providers.openai_api import OpenAIProvider
from providers.google_api import GoogleProvider
from providers.xai_api import XAIProvider
from tracker import LocalTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


class BudgetDashboardApp(rumps.App):
    """Main menu bar application."""

    def __init__(self):
        super().__init__("AI Budget", quit_button=None)

        self.cfg = app_config.load_config()
        self._last_month = datetime.now(timezone.utc).month

        # Initialize local tracker
        log_path = app_config.get_log_path(self.cfg)
        self.tracker = LocalTracker(log_path)

        # Initialize providers
        xai_team_id = app_config.get_xai_team_id(self.cfg)
        self.providers = {
            "anthropic": AnthropicProvider(),
            "openai": OpenAIProvider(),
            "google": GoogleProvider(tracker=self.tracker),
            "xai": XAIProvider(tracker=self.tracker, team_id=xai_team_id),
        }

        # Usage data cache — protected by _data_lock
        self.usage_data: dict[str, UsageData] = {}
        self._data_lock = threading.Lock()

        # Refresh concurrency — only one refresh at a time
        self._refresh_lock = threading.Lock()

        # Build initial menu
        self._build_menu()

        # Set up auto-refresh timer
        interval_min = app_config.get_refresh_interval(self.cfg)
        self.timer = rumps.Timer(self._auto_refresh, interval_min * 60)
        self.timer.start()

        # Initial fetch in background
        self._refresh_in_background()

    def _build_menu(self) -> None:
        """Build the dropdown menu structure."""
        now = datetime.now(timezone.utc)
        month_name = now.strftime("%B %Y")

        self.menu.clear()

        # Header
        header = rumps.MenuItem(f"AI Budget — {month_name}")
        header.set_callback(None)
        self.menu.add(header)
        self.menu.add(rumps.separator)

        # Provider sections
        provider_order = ["anthropic", "openai", "google", "xai"]
        with self._data_lock:
            usage_snapshot = dict(self.usage_data)

        for pid in provider_order:
            if not app_config.is_provider_enabled(self.cfg, pid):
                continue
            usage = usage_snapshot.get(pid)
            if usage:
                self._add_provider_menu_items(usage)
            else:
                budget = app_config.get_provider_budget(self.cfg, pid)
                name = app_config.PROVIDER_DISPLAY_NAMES.get(pid, pid)
                placeholder = rumps.MenuItem(f"{name}    $0.00/${budget:.0f}")
                placeholder.set_callback(None)
                self.menu.add(placeholder)
                self.menu.add(rumps.separator)

        # Total line
        total_spend, total_budget = self._get_totals()
        total_item = rumps.MenuItem(f"Total: ${total_spend:.2f} / ${total_budget:.0f}")
        total_item.set_callback(None)
        self.menu.add(total_item)
        self.menu.add(rumps.separator)

        # Last updated
        self._updated_item = rumps.MenuItem(self._format_updated_time())
        self._updated_item.set_callback(None)
        self.menu.add(self._updated_item)

        # Refresh button
        refresh_item = rumps.MenuItem("Refresh Now")
        refresh_item.set_callback(self._on_refresh_click)
        self.menu.add(refresh_item)

        self.menu.add(rumps.separator)

        # Quit
        quit_item = rumps.MenuItem("Quit")
        quit_item.set_callback(self._on_quit)
        self.menu.add(quit_item)

    def _add_provider_menu_items(self, usage: UsageData) -> None:
        """Add menu items for a single provider."""
        # Provider name + spend
        spend_line = f"{usage.provider_name}    {usage.format_spend()}"
        item = rumps.MenuItem(spend_line)
        item.set_callback(None)
        self.menu.add(item)

        # Progress bar
        bar = self._make_progress_bar(usage.usage_percent)
        bar_item = rumps.MenuItem(f"  {bar}  {usage.usage_percent:.0f}%")
        bar_item.set_callback(None)
        self.menu.add(bar_item)

        # Token counts
        if usage.tokens_in > 0 or usage.tokens_out > 0:
            tokens_item = rumps.MenuItem(f"  {usage.format_tokens()}")
            tokens_item.set_callback(None)
            self.menu.add(tokens_item)

        self.menu.add(rumps.separator)

    def _make_progress_bar(self, percent: float, width: int = 16) -> str:
        """Create a text-based progress bar."""
        filled = int(width * min(percent, 100.0) / 100.0)
        empty = width - filled

        if percent >= 85:
            fill_char = "\u2588"  # Red zone — full block
        elif percent >= 60:
            fill_char = "\u2588"  # Yellow zone
        else:
            fill_char = "\u2588"  # Green zone

        return fill_char * filled + "\u2591" * empty

    def _get_totals(self) -> tuple[float, float]:
        """Get total spend and total budget across enabled providers."""
        total_spend = 0.0
        total_budget = app_config.get_total_budget(self.cfg)
        with self._data_lock:
            for pid, usage in self.usage_data.items():
                if app_config.is_provider_enabled(self.cfg, pid):
                    total_spend += usage.current_spend
        return total_spend, total_budget

    def _update_title(self) -> None:
        """Update the menu bar title with total spend/budget."""
        total_spend, total_budget = self._get_totals()
        if total_budget > 0:
            percent = (total_spend / total_budget) * 100
            if percent >= 85:
                indicator = "\U0001f534"  # Red
            elif percent >= 60:
                indicator = "\U0001f7e1"  # Yellow
            else:
                indicator = "\U0001f7e2"  # Green

            display_mode = self.cfg.get("displayMode", "compact")
            if display_mode == "compact":
                self.title = f"${total_spend:.2f}/${total_budget:.0f}"
            else:
                self.title = f"{indicator} ${total_spend:.2f}"
        else:
            self.title = "AI Budget"

    def _format_updated_time(self) -> str:
        """Format the 'last updated' string."""
        latest = None
        with self._data_lock:
            for usage in self.usage_data.values():
                if latest is None or usage.last_updated > latest:
                    latest = usage.last_updated

        if latest is None:
            return "\u21bb Not yet updated"

        now = datetime.now(timezone.utc)
        # Handle naive datetimes
        if latest.tzinfo is None:
            diff = datetime.now() - latest
        else:
            diff = now - latest
        minutes = int(diff.total_seconds() / 60)

        if minutes < 1:
            return "\u21bb Updated just now"
        elif minutes == 1:
            return "\u21bb Updated 1 min ago"
        else:
            return f"\u21bb Updated {minutes} min ago"

    def _refresh_data(self) -> None:
        """Fetch usage data from all enabled providers.

        Preserves last-known-good data on per-provider failure:
        only updates usage_data for a provider if fetch succeeds
        (non-zero spend or explicit zero from API).
        """
        # Check for month rollover
        current_month = datetime.now(timezone.utc).month
        if current_month != self._last_month:
            self._last_month = current_month
            notifier.reset_alerts()
            with self._data_lock:
                self.usage_data.clear()
            logger.info("Month rollover detected — alerts reset.")

        thresholds = app_config.get_alert_thresholds(self.cfg)

        for pid, provider in self.providers.items():
            if not app_config.is_provider_enabled(self.cfg, pid):
                continue

            api_key = keychain.get_api_key(pid)
            budget = app_config.get_provider_budget(self.cfg, pid)

            logger.info("Fetching usage for %s...", pid)
            try:
                usage = provider.fetch_usage(api_key, budget)
            except Exception as e:
                logger.error("Provider %s fetch raised: %s", pid, e)
                continue

            if usage.error:
                logger.warning("Provider %s partial error: %s", pid, usage.error)

            with self._data_lock:
                self.usage_data[pid] = usage

            # Check budget alerts
            notifier.check_and_notify(
                provider_name=usage.provider_name,
                provider_id=pid,
                usage_percent=usage.usage_percent,
                thresholds=thresholds,
            )

    def _refresh_in_background(self) -> None:
        """Run data refresh in a background thread.

        Uses _refresh_lock to prevent overlapping refreshes.
        Schedules UI updates on the main thread via rumps timer.
        """
        def _do_refresh():
            if not self._refresh_lock.acquire(blocking=False):
                logger.debug("Refresh already in progress, skipping.")
                return
            try:
                self._refresh_data()
            except Exception as e:
                logger.error("Background refresh failed: %s", e)
            finally:
                self._refresh_lock.release()
                # Schedule UI update on main thread
                self._schedule_ui_update()

        thread = threading.Thread(target=_do_refresh, daemon=True)
        thread.start()

    def _schedule_ui_update(self) -> None:
        """Dispatch UI update to the main thread.

        Uses PyObjC AppHelper.callAfter to safely mutate rumps UI elements
        from a background thread. This is a macOS-only app, so PyObjC is
        always available as a hard dependency.
        """
        AppHelper.callAfter(self._do_ui_update)

    def _do_ui_update(self) -> None:
        """Update UI elements — must be called on the main thread."""
        self._update_title()
        self._build_menu()

    def _auto_refresh(self, _timer) -> None:
        """Timer callback for auto-refresh."""
        self._refresh_in_background()

    def _on_refresh_click(self, _sender) -> None:
        """Handle manual refresh button click."""
        self.title = "AI Budget \u21bb"
        self._refresh_in_background()

    def _on_quit(self, _sender) -> None:
        """Handle quit button click."""
        rumps.quit_application()


def main():
    """Entry point."""
    app = BudgetDashboardApp()
    app.run()


if __name__ == "__main__":
    main()
