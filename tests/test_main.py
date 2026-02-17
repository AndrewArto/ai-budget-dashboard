"""Tests for main app module."""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

# We need to mock rumps before importing main, since rumps requires macOS GUI
import sys


class FakeMenuItem:
    def __init__(self, title="", callback=None):
        self.title = title
        self._callback = callback

    def set_callback(self, cb):
        self._callback = cb


class FakeMenu:
    def __init__(self):
        self._items = []

    def clear(self):
        self._items.clear()

    def add(self, item):
        self._items.append(item)

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)


class FakeTimer:
    def __init__(self, callback, interval):
        self.callback = callback
        self.interval = interval
        self.is_alive = False

    def start(self):
        self.is_alive = True

    def stop(self):
        self.is_alive = False


class FakeApp:
    def __init__(self, name, **kwargs):
        self.name = name
        self.title = name
        self.menu = FakeMenu()

    def run(self):
        pass


# Create fake rumps module
fake_rumps = MagicMock()
fake_rumps.App = FakeApp
fake_rumps.MenuItem = FakeMenuItem
fake_rumps.Timer = FakeTimer
fake_rumps.separator = "---"
fake_rumps.quit_application = MagicMock()

# Patch rumps before importing main
sys.modules["rumps"] = fake_rumps

# Mock PyObjCTools.AppHelper (hard dependency — macOS-only app)
import types

fake_apphelper = types.ModuleType("PyObjCTools.AppHelper")
fake_apphelper.callAfter = MagicMock()

fake_pyobjctools = types.ModuleType("PyObjCTools")
fake_pyobjctools.AppHelper = fake_apphelper

sys.modules["PyObjCTools"] = fake_pyobjctools
sys.modules["PyObjCTools.AppHelper"] = fake_apphelper

from providers.base import UsageData


class TestBudgetDashboardApp:
    """Test the main app logic without requiring macOS GUI."""

    @patch("keychain.get_api_key", return_value=None)
    @patch("config.load_config")
    def test_app_initialization(self, mock_config, mock_keychain):
        mock_config.return_value = {
            "providers": {
                "anthropic": {"budget": 80.0, "enabled": True},
                "openai": {"budget": 60.0, "enabled": True},
                "google": {"budget": 30.0, "enabled": True},
                "xai": {"budget": 30.0, "enabled": True},
            },
            "refreshIntervalMinutes": 15,
            "alertThresholds": [80, 95],
            "displayMode": "compact",
            "localTrackingLogPath": "/tmp/test-logs/",
        }

        import main as app_main

        app = app_main.BudgetDashboardApp()
        assert app.title is not None
        assert len(app.providers) == 4

    @patch("keychain.get_api_key", return_value=None)
    @patch("config.load_config")
    def test_get_totals(self, mock_config, mock_keychain):
        mock_config.return_value = {
            "providers": {
                "anthropic": {"budget": 80.0, "enabled": True},
                "openai": {"budget": 60.0, "enabled": True},
                "google": {"budget": 30.0, "enabled": True},
                "xai": {"budget": 30.0, "enabled": True},
            },
            "refreshIntervalMinutes": 15,
            "alertThresholds": [80, 95],
            "displayMode": "compact",
            "localTrackingLogPath": "/tmp/test-logs/",
        }

        import main as app_main

        app = app_main.BudgetDashboardApp()
        app.usage_data = {
            "anthropic": UsageData("anthropic", "Anthropic", current_spend=28.40, monthly_budget=80.0),
            "openai": UsageData("openai", "OpenAI", current_spend=12.30, monthly_budget=60.0),
        }

        total_spend, total_budget = app._get_totals()
        assert total_spend == pytest.approx(40.70)
        assert total_budget == 200.0

    @patch("keychain.get_api_key", return_value=None)
    @patch("config.load_config")
    def test_progress_bar(self, mock_config, mock_keychain):
        mock_config.return_value = {
            "providers": {
                "anthropic": {"budget": 80.0, "enabled": True},
                "openai": {"budget": 60.0, "enabled": True},
                "google": {"budget": 30.0, "enabled": True},
                "xai": {"budget": 30.0, "enabled": True},
            },
            "refreshIntervalMinutes": 15,
            "alertThresholds": [80, 95],
            "displayMode": "compact",
            "localTrackingLogPath": "/tmp/test-logs/",
        }

        import main as app_main

        app = app_main.BudgetDashboardApp()

        bar_50 = app._make_progress_bar(50.0, width=10)
        assert len(bar_50) == 10
        assert bar_50.count("\u2588") == 5
        assert bar_50.count("\u2591") == 5

        bar_100 = app._make_progress_bar(100.0, width=10)
        assert bar_100.count("\u2588") == 10

        bar_0 = app._make_progress_bar(0.0, width=10)
        assert bar_0.count("\u2591") == 10

    @patch("keychain.get_api_key", return_value=None)
    @patch("config.load_config")
    def test_update_title_compact(self, mock_config, mock_keychain):
        mock_config.return_value = {
            "providers": {
                "anthropic": {"budget": 80.0, "enabled": True},
                "openai": {"budget": 60.0, "enabled": True},
                "google": {"budget": 30.0, "enabled": True},
                "xai": {"budget": 30.0, "enabled": True},
            },
            "refreshIntervalMinutes": 15,
            "alertThresholds": [80, 95],
            "displayMode": "compact",
            "localTrackingLogPath": "/tmp/test-logs/",
        }

        import main as app_main

        app = app_main.BudgetDashboardApp()
        app.usage_data = {
            "anthropic": UsageData("anthropic", "Anthropic", current_spend=47.23, monthly_budget=80.0),
        }

        app._update_title()
        assert "$47.23" in app.title

    @patch("keychain.get_api_key", return_value=None)
    @patch("config.load_config")
    def test_schedule_ui_update_always_uses_apphelper(self, mock_config, mock_keychain):
        """PyObjC is a hard dependency — _schedule_ui_update always uses AppHelper.callAfter."""
        mock_config.return_value = {
            "providers": {
                "anthropic": {"budget": 80.0, "enabled": True},
                "openai": {"budget": 60.0, "enabled": True},
                "google": {"budget": 30.0, "enabled": True},
                "xai": {"budget": 30.0, "enabled": True},
            },
            "refreshIntervalMinutes": 15,
            "alertThresholds": [80, 95],
            "displayMode": "compact",
            "localTrackingLogPath": "/tmp/test-logs/",
            "xaiTeamId": "",
        }

        import main as app_main

        mock_callafter = MagicMock()

        # Temporarily inject mock AppHelper
        import types
        fake_helper = types.ModuleType("PyObjCTools.AppHelper")
        fake_helper.callAfter = mock_callafter

        with patch.object(app_main, "AppHelper", fake_helper):
            app = app_main.BudgetDashboardApp()
            # Init triggers background refresh which also calls _schedule_ui_update
            import time
            time.sleep(0.1)
            mock_callafter.reset_mock()

            app._schedule_ui_update()
            mock_callafter.assert_called_once_with(app._do_ui_update)

    @patch("keychain.get_api_key", return_value=None)
    @patch("config.load_config")
    def test_pyobjc_is_hard_dependency(self, mock_config, mock_keychain):
        """PyObjC AppHelper is imported unconditionally — no try/except fallback."""
        mock_config.return_value = {
            "providers": {
                "anthropic": {"budget": 80.0, "enabled": True},
                "openai": {"budget": 60.0, "enabled": True},
                "google": {"budget": 30.0, "enabled": True},
                "xai": {"budget": 30.0, "enabled": True},
            },
            "refreshIntervalMinutes": 15,
            "alertThresholds": [80, 95],
            "displayMode": "compact",
            "localTrackingLogPath": "/tmp/test-logs/",
            "xaiTeamId": "",
        }

        import main as app_main

        # Verify there is no _has_apphelper flag (removed — PyObjC is always required)
        assert not hasattr(app_main, "_has_apphelper")

        # Verify AppHelper is imported at module level
        assert hasattr(app_main, "AppHelper")

        # Verify no timer fallback method exists
        app = app_main.BudgetDashboardApp()
        assert not hasattr(app, "_do_ui_update_timer")

    @patch("keychain.get_api_key", return_value=None)
    @patch("config.load_config")
    def test_refresh_preserves_data_on_provider_error(self, mock_config, mock_keychain):
        """When a provider raises, old data should be preserved."""
        mock_config.return_value = {
            "providers": {
                "anthropic": {"budget": 80.0, "enabled": True},
                "openai": {"budget": 60.0, "enabled": True},
                "google": {"budget": 30.0, "enabled": True},
                "xai": {"budget": 30.0, "enabled": True},
            },
            "refreshIntervalMinutes": 15,
            "alertThresholds": [80, 95],
            "displayMode": "compact",
            "localTrackingLogPath": "/tmp/test-logs/",
            "xaiTeamId": "",
        }

        import main as app_main
        import time

        app = app_main.BudgetDashboardApp()

        # Wait for init background refresh to complete
        time.sleep(0.2)

        # Set existing data AFTER init refresh completed
        old_data = UsageData("anthropic", "Anthropic", current_spend=25.0, monthly_budget=80.0)
        with app._data_lock:
            app.usage_data["anthropic"] = old_data

        # Make anthropic provider raise
        app.providers["anthropic"].fetch_usage = MagicMock(side_effect=Exception("API down"))

        # Run refresh — should preserve old data for anthropic
        app._refresh_data()

        with app._data_lock:
            assert app.usage_data["anthropic"] is old_data
            assert app.usage_data["anthropic"].current_spend == 25.0

    @patch("keychain.get_api_key", return_value=None)
    @patch("config.load_config")
    def test_format_updated_time_uses_lock(self, mock_config, mock_keychain):
        """_format_updated_time should acquire _data_lock."""
        mock_config.return_value = {
            "providers": {
                "anthropic": {"budget": 80.0, "enabled": True},
                "openai": {"budget": 60.0, "enabled": True},
                "google": {"budget": 30.0, "enabled": True},
                "xai": {"budget": 30.0, "enabled": True},
            },
            "refreshIntervalMinutes": 15,
            "alertThresholds": [80, 95],
            "displayMode": "compact",
            "localTrackingLogPath": "/tmp/test-logs/",
            "xaiTeamId": "",
        }

        import main as app_main

        app = app_main.BudgetDashboardApp()
        app.usage_data["anthropic"] = UsageData(
            "anthropic", "Anthropic", current_spend=10.0
        )

        # Should not deadlock — lock is acquired and released properly
        result = app._format_updated_time()
        assert "\u21bb" in result  # Contains refresh symbol
