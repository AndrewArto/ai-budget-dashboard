"""Tests for main app module."""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

import sys
import types


# Mock macOS-only dependencies before importing main
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


fake_rumps = MagicMock()
fake_rumps.App = FakeApp
fake_rumps.MenuItem = FakeMenuItem
fake_rumps.Timer = FakeTimer
fake_rumps.separator = "---"
fake_rumps.quit_application = MagicMock()
sys.modules["rumps"] = fake_rumps

fake_apphelper = types.ModuleType("PyObjCTools.AppHelper")
fake_apphelper.callAfter = MagicMock()
fake_pyobjctools = types.ModuleType("PyObjCTools")
fake_pyobjctools.AppHelper = fake_apphelper
sys.modules["PyObjCTools"] = fake_pyobjctools
sys.modules["PyObjCTools.AppHelper"] = fake_apphelper

from providers.base import UsageData


def _default_config(**overrides):
    cfg = {
        "providers": {
            "anthropic": {"budget": 80.0, "enabled": True},
            "openai": {"budget": 60.0, "enabled": True},
            "google": {"budget": 30.0, "enabled": True},
            "xai": {"budget": 30.0, "enabled": True},
        },
        "refreshIntervalMinutes": 15,
        "alertThresholds": [80, 95],
        "displayMode": "compact",
        "agentsPath": "/tmp/test-agents/",
    }
    cfg.update(overrides)
    return cfg


class TestBudgetDashboardApp:
    @patch("config.load_config")
    def test_app_initialization(self, mock_config):
        mock_config.return_value = _default_config()

        import main as app_main
        app = app_main.BudgetDashboardApp()
        assert app.title is not None
        assert len(app.providers) == 4

    @patch("config.load_config")
    def test_get_totals(self, mock_config):
        mock_config.return_value = _default_config()

        import main as app_main
        app = app_main.BudgetDashboardApp()
        app.usage_data = {
            "anthropic": UsageData("anthropic", "Anthropic", current_spend=28.40, monthly_budget=80.0),
            "openai": UsageData("openai", "OpenAI", current_spend=12.30, monthly_budget=60.0),
        }

        total_spend, total_budget = app._get_totals()
        assert total_spend == pytest.approx(40.70)
        assert total_budget == 200.0

    @patch("config.load_config")
    def test_progress_bar(self, mock_config):
        mock_config.return_value = _default_config()

        import main as app_main
        app = app_main.BudgetDashboardApp()

        bar_50 = app._make_progress_bar(50.0, width=10)
        assert len(bar_50) == 10
        assert bar_50.count("\u2588") == 5
        assert bar_50.count("\u2591") == 5

    @patch("config.load_config")
    def test_update_title_compact(self, mock_config):
        mock_config.return_value = _default_config()

        import main as app_main
        app = app_main.BudgetDashboardApp()
        app.usage_data = {
            "anthropic": UsageData("anthropic", "Anthropic", current_spend=47.23, monthly_budget=80.0),
        }

        app._update_title()
        assert "$47.23" in app.title

    @patch("config.load_config")
    def test_refresh_preserves_data_on_provider_error(self, mock_config):
        mock_config.return_value = _default_config()

        import main as app_main
        import time

        app = app_main.BudgetDashboardApp()
        time.sleep(0.2)

        old_data = UsageData("anthropic", "Anthropic", current_spend=25.0, monthly_budget=80.0)
        with app._data_lock:
            app.usage_data["anthropic"] = old_data

        app.providers["anthropic"].fetch_usage = MagicMock(side_effect=Exception("down"))
        app._refresh_data()

        with app._data_lock:
            assert app.usage_data["anthropic"] is old_data

    @patch("config.load_config")
    def test_format_updated_time(self, mock_config):
        mock_config.return_value = _default_config()

        import main as app_main
        app = app_main.BudgetDashboardApp()
        app.usage_data["anthropic"] = UsageData("anthropic", "Anthropic", current_spend=10.0)

        result = app._format_updated_time()
        assert "\u21bb" in result
