"""Tests for config module."""

import json
import os
import tempfile

import pytest

import config as app_config


@pytest.fixture
def tmp_config_file():
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {
                "providers": {
                    "anthropic": {"budget": 100.0, "enabled": True},
                    "openai": {"budget": 50.0, "enabled": True},
                    "google": {"budget": 20.0, "enabled": False},
                    "xai": {"budget": 10.0, "enabled": True},
                },
                "refreshIntervalMinutes": 10,
                "alertThresholds": [75, 90],
                "displayMode": "icon",
                "localTrackingLogPath": "/tmp/test-logs/",
            },
            f,
        )
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
def tmp_config_dir():
    """Create a temporary directory for config."""
    with tempfile.TemporaryDirectory() as d:
        yield os.path.join(d, "config.json")


class TestLoadConfig:
    def test_load_defaults_when_no_file(self):
        config = app_config.load_config("/nonexistent/path/config.json")
        assert config["providers"]["anthropic"]["budget"] == 80.0
        assert config["refreshIntervalMinutes"] == 15
        assert config["alertThresholds"] == [80, 95]

    def test_load_from_file(self, tmp_config_file):
        config = app_config.load_config(tmp_config_file)
        assert config["providers"]["anthropic"]["budget"] == 100.0
        assert config["providers"]["openai"]["budget"] == 50.0
        assert config["refreshIntervalMinutes"] == 10

    def test_merge_with_defaults(self, tmp_config_dir):
        """Partial config should be merged with defaults."""
        partial = {"providers": {"anthropic": {"budget": 200.0, "enabled": True}}}
        with open(tmp_config_dir, "w") as f:
            json.dump(partial, f)

        config = app_config.load_config(tmp_config_dir)
        # Custom value
        assert config["providers"]["anthropic"]["budget"] == 200.0
        # Default values preserved
        assert config["providers"]["openai"]["budget"] == 60.0
        assert config["refreshIntervalMinutes"] == 15

    def test_bad_json_returns_defaults(self, tmp_config_dir):
        """Invalid JSON should not crash; returns defaults."""
        with open(tmp_config_dir, "w") as f:
            f.write("{invalid json content!!!")

        config = app_config.load_config(tmp_config_dir)
        assert config["providers"]["anthropic"]["budget"] == 80.0
        assert config["refreshIntervalMinutes"] == 15

    def test_non_dict_json_returns_defaults(self, tmp_config_dir):
        """JSON array instead of object should use defaults."""
        with open(tmp_config_dir, "w") as f:
            json.dump([1, 2, 3], f)

        config = app_config.load_config(tmp_config_dir)
        assert config["providers"]["anthropic"]["budget"] == 80.0

    def test_auto_create_config_on_first_run(self):
        """Config should be auto-created when file doesn't exist."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "subdir", "config.json")
            config = app_config.load_config(path)
            assert config["providers"]["anthropic"]["budget"] == 80.0
            # File should have been created
            assert os.path.exists(path)
            # File should contain valid JSON with defaults
            with open(path, "r") as f:
                saved = json.load(f)
            assert saved["refreshIntervalMinutes"] == 15


class TestSaveConfig:
    def test_save_and_reload(self, tmp_config_dir):
        config = app_config.DEFAULT_CONFIG.copy()
        config["refreshIntervalMinutes"] = 5
        app_config.save_config(config, tmp_config_dir)

        loaded = app_config.load_config(tmp_config_dir)
        assert loaded["refreshIntervalMinutes"] == 5


class TestValidateConfig:
    def test_refresh_interval_clamped_low(self):
        config = app_config._validate_config({"refreshIntervalMinutes": 0, "providers": {}})
        assert config["refreshIntervalMinutes"] == 1

    def test_refresh_interval_clamped_high(self):
        config = app_config._validate_config({"refreshIntervalMinutes": 9999, "providers": {}})
        assert config["refreshIntervalMinutes"] == 1440

    def test_refresh_interval_non_numeric(self):
        config = app_config._validate_config({"refreshIntervalMinutes": "abc", "providers": {}})
        assert config["refreshIntervalMinutes"] == 15

    def test_alert_thresholds_invalid_values(self):
        config = app_config._validate_config({"alertThresholds": [0, 101, "bad", 50], "providers": {}})
        assert 50 in config["alertThresholds"]
        assert 0 not in config["alertThresholds"]
        assert 101 not in config["alertThresholds"]

    def test_alert_thresholds_not_a_list(self):
        config = app_config._validate_config({"alertThresholds": "not_a_list", "providers": {}})
        assert config["alertThresholds"] == [80, 95]

    def test_display_mode_invalid(self):
        config = app_config._validate_config({"displayMode": "invalid", "providers": {}})
        assert config["displayMode"] == "compact"

    def test_negative_budget_clamped(self):
        config = app_config._validate_config({
            "providers": {"anthropic": {"budget": -50, "enabled": True}},
        })
        assert config["providers"]["anthropic"]["budget"] == 0.0

    def test_non_numeric_budget(self):
        config = app_config._validate_config({
            "providers": {"anthropic": {"budget": "not_a_number", "enabled": True}},
        })
        assert config["providers"]["anthropic"]["budget"] == 0.0

    def test_provider_config_not_dict(self):
        config = app_config._validate_config({
            "providers": {"anthropic": "invalid"},
        })
        assert config["providers"]["anthropic"]["budget"] == 0.0
        assert config["providers"]["anthropic"]["enabled"] is False

    def test_empty_agents_path(self):
        config = app_config._validate_config({"agentsPath": "", "providers": {}})
        assert config["agentsPath"] == "~/.openclaw/agents"


class TestHelpers:
    def test_get_provider_budget(self):
        config = app_config.load_config("/nonexistent")
        assert app_config.get_provider_budget(config, "anthropic") == 80.0
        assert app_config.get_provider_budget(config, "unknown") == 0.0

    def test_is_provider_enabled(self):
        config = app_config.load_config("/nonexistent")
        assert app_config.is_provider_enabled(config, "anthropic") is True
        assert app_config.is_provider_enabled(config, "unknown") is False

    def test_get_total_budget(self):
        config = app_config.load_config("/nonexistent")
        # All providers enabled: 80 + 60 + 30 + 30 = 200
        assert app_config.get_total_budget(config) == 200.0

    def test_get_total_budget_with_disabled(self, tmp_config_file):
        config = app_config.load_config(tmp_config_file)
        # Google disabled: 100 + 50 + 10 = 160
        assert app_config.get_total_budget(config) == 160.0

    def test_get_refresh_interval(self):
        config = app_config.load_config("/nonexistent")
        assert app_config.get_refresh_interval(config) == 15

    def test_get_alert_thresholds(self):
        config = app_config.load_config("/nonexistent")
        assert app_config.get_alert_thresholds(config) == [80, 95]

    def test_get_agents_path(self):
        config = app_config.load_config("/nonexistent")
        path = app_config.get_agents_path(config)
        assert "openclaw/agents" in path
        assert "~" not in path  # Should be expanded
