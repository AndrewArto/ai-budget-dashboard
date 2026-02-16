"""Tests for keychain module."""

from unittest.mock import patch, MagicMock

import keychain


class TestGetApiKey:
    @patch("keychain.keyring.get_password")
    def test_returns_key(self, mock_get):
        mock_get.return_value = "sk-test-key-123"
        result = keychain.get_api_key("anthropic")
        assert result == "sk-test-key-123"
        mock_get.assert_called_once_with("ai-budget-dashboard", "anthropic-api-key")

    @patch("keychain.keyring.get_password")
    def test_returns_none_when_not_found(self, mock_get):
        mock_get.return_value = None
        result = keychain.get_api_key("openai")
        assert result is None

    @patch("keychain.keyring.get_password")
    def test_returns_none_on_error(self, mock_get):
        mock_get.side_effect = Exception("Keychain locked")
        result = keychain.get_api_key("anthropic")
        assert result is None

    @patch("keychain.keyring.get_password")
    def test_unknown_provider_uses_default_account(self, mock_get):
        mock_get.return_value = "key-123"
        result = keychain.get_api_key("custom-provider")
        mock_get.assert_called_once_with("ai-budget-dashboard", "custom-provider-api-key")


class TestSetApiKey:
    @patch("keychain.keyring.set_password")
    def test_stores_key(self, mock_set):
        keychain.set_api_key("anthropic", "sk-new-key")
        mock_set.assert_called_once_with(
            "ai-budget-dashboard", "anthropic-api-key", "sk-new-key"
        )


class TestDeleteApiKey:
    @patch("keychain.keyring.delete_password")
    def test_deletes_key(self, mock_delete):
        keychain.delete_api_key("openai")
        mock_delete.assert_called_once_with("ai-budget-dashboard", "openai-api-key")

    @patch("keychain.keyring.delete_password")
    def test_handles_missing_key(self, mock_delete):
        import keyring as kr
        mock_delete.side_effect = kr.errors.PasswordDeleteError("Not found")
        # Should not raise
        keychain.delete_api_key("openai")
