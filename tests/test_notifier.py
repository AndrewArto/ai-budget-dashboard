"""Tests for the notifier module."""

from unittest.mock import patch, MagicMock

import notifier


class TestCheckAndNotify:
    def setup_method(self):
        """Reset alerts before each test."""
        notifier.reset_alerts()

    @patch("notifier._send_notification")
    def test_below_threshold_no_alert(self, mock_send):
        notifier.check_and_notify("Anthropic", "anthropic", 50.0, [80, 95])
        mock_send.assert_not_called()

    @patch("notifier._send_notification")
    def test_at_threshold_sends_alert(self, mock_send):
        notifier.check_and_notify("Anthropic", "anthropic", 80.0, [80, 95])
        mock_send.assert_called_once()
        assert "80%" in mock_send.call_args[1]["message"] or "80%" in mock_send.call_args[0][1]

    @patch("notifier._send_notification")
    def test_above_threshold_sends_alert(self, mock_send):
        notifier.check_and_notify("OpenAI", "openai", 90.0, [80, 95])
        mock_send.assert_called_once()

    @patch("notifier._send_notification")
    def test_duplicate_alert_not_sent(self, mock_send):
        notifier.check_and_notify("Anthropic", "anthropic", 85.0, [80, 95])
        assert mock_send.call_count == 1

        # Same threshold, same provider — should NOT send again
        notifier.check_and_notify("Anthropic", "anthropic", 87.0, [80, 95])
        assert mock_send.call_count == 1

    @patch("notifier._send_notification")
    def test_multiple_thresholds(self, mock_send):
        notifier.check_and_notify("xAI", "xai", 96.0, [80, 95])
        # Should trigger both 80% and 95% thresholds
        assert mock_send.call_count == 2

    @patch("notifier._send_notification")
    def test_different_providers_independent(self, mock_send):
        notifier.check_and_notify("Anthropic", "anthropic", 85.0, [80, 95])
        notifier.check_and_notify("OpenAI", "openai", 85.0, [80, 95])
        assert mock_send.call_count == 2

    @patch("notifier._send_notification")
    def test_reset_alerts(self, mock_send):
        notifier.check_and_notify("Anthropic", "anthropic", 85.0, [80, 95])
        assert mock_send.call_count == 1

        notifier.reset_alerts()

        notifier.check_and_notify("Anthropic", "anthropic", 85.0, [80, 95])
        assert mock_send.call_count == 2

    @patch("notifier._send_notification", return_value=False)
    def test_failed_notification_not_marked_sent(self, mock_send):
        """If notification delivery fails, alert should NOT be marked as sent."""
        notifier.check_and_notify("Anthropic", "anthropic", 85.0, [80, 95])
        mock_send.assert_called_once()

        # Since delivery failed, the alert should retry on next call
        notifier.check_and_notify("Anthropic", "anthropic", 85.0, [80, 95])
        assert mock_send.call_count == 2

    @patch("notifier._send_notification")
    def test_retry_succeeds_after_failure(self, mock_send):
        """Alert retries on next refresh and succeeds."""
        # First attempt fails
        mock_send.return_value = False
        notifier.check_and_notify("Anthropic", "anthropic", 85.0, [80, 95])
        assert mock_send.call_count == 1

        # Second attempt succeeds
        mock_send.return_value = True
        notifier.check_and_notify("Anthropic", "anthropic", 85.0, [80, 95])
        assert mock_send.call_count == 2

        # Third call: already sent, should NOT retry
        notifier.check_and_notify("Anthropic", "anthropic", 85.0, [80, 95])
        assert mock_send.call_count == 2


class TestSendNotification:
    @patch("notifier.subprocess.run")
    def test_sends_osascript(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = notifier._send_notification("Test Title", "Test message")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"
        assert "Test Title" in args[2]
        assert "Test message" in args[2]
        assert result is True

    @patch("notifier.subprocess.run")
    def test_returns_false_on_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stderr=b"some error"
        )
        result = notifier._send_notification("Title", "Message")
        assert result is False

    @patch("notifier.subprocess.run")
    def test_handles_failure(self, mock_run):
        mock_run.side_effect = FileNotFoundError("osascript not found")
        result = notifier._send_notification("Title", "Message")
        assert result is False

    @patch("notifier.subprocess.run")
    def test_handles_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=5)
        result = notifier._send_notification("Title", "Message")
        assert result is False


class TestEscapeApplescript:
    def test_escapes_quotes(self):
        result = notifier._escape_applescript('He said "hello"')
        assert result == 'He said \\"hello\\"'

    def test_escapes_backslash(self):
        result = notifier._escape_applescript("path\\to\\file")
        assert result == "path\\\\to\\\\file"

    def test_plain_string(self):
        result = notifier._escape_applescript("simple text")
        assert result == "simple text"
