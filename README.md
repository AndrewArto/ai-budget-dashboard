# AI Budget Dashboard

macOS menu bar application that tracks AI API spending across four providers: **Anthropic**, **OpenAI**, **Google (Gemini)**, and **xAI (Grok)**.

Displays real-time usage for the current calendar month with per-provider breakdown, budget alerts, and auto-refresh.

## Features

- **Menu bar display** — total spend/budget at a glance (`$47.23/$200`)
- **Per-provider breakdown** — click to see spend, budget, progress bar, and token counts
- **Provider API integrations** — Anthropic Admin API, OpenAI Costs API
- **Local tracking fallback** — for Google via OpenClaw log parsing
- **xAI Management API** — billing data from xAI Management API with local tracking fallback
- **Budget alerts** — macOS notifications at 80% and 95% thresholds
- **Auto-refresh** — configurable interval (default 15 min)
- **Manual refresh** — click to update immediately
- **Calendar month scope** — auto-resets on the 1st of each month
- **macOS Keychain** — API keys stored securely via `keyring`

## Requirements

- macOS 12+
- Python 3.9+

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Store API keys in macOS Keychain (interactive — keys are not saved in shell history)
python3 -c "
import keychain, getpass
keychain.set_api_key('anthropic', getpass.getpass('Anthropic Admin API key: '))
keychain.set_api_key('openai', getpass.getpass('OpenAI Admin API key: '))
"

# Run the app
python3 main.py
```

## Configuration

Settings are stored in `~/.config/ai-budget/config.json`. The file is auto-created with defaults on first run.

```json
{
  "providers": {
    "anthropic": { "budget": 80, "enabled": true },
    "openai": { "budget": 60, "enabled": true },
    "google": { "budget": 30, "enabled": true },
    "xai": { "budget": 30, "enabled": true }
  },
  "refreshIntervalMinutes": 15,
  "alertThresholds": [80, 95],
  "displayMode": "compact",
  "localTrackingLogPath": "~/.openclaw/logs/",
  "xaiTeamId": ""
}
```

### Configuration Options

| Setting | Description | Default |
|---------|-------------|---------|
| `providers.*.budget` | Monthly budget in USD per provider | 80/60/30/30 |
| `providers.*.enabled` | Enable/disable provider tracking | `true` |
| `refreshIntervalMinutes` | Auto-refresh interval | 15 |
| `alertThresholds` | Budget % thresholds for notifications | [80, 95] |
| `displayMode` | Menu bar display: `compact` or `icon` | `compact` |
| `localTrackingLogPath` | Path to OpenClaw logs for fallback tracking | `~/.openclaw/logs/` |
| `xaiTeamId` | xAI team ID for Management API billing | `""` |

## API Key Setup

API keys are stored in the macOS Keychain (not in config files):

```python
import keychain

# Set keys
keychain.set_api_key("anthropic", "sk-ant-admin-...")
keychain.set_api_key("openai", "sk-admin-...")

# Verify keys are stored
print(keychain.get_api_key("anthropic"))
```

## xAI Management API

xAI billing data is fetched from the [xAI Management API](https://management-api.x.ai). Configure your team ID in `config.json`:

```json
{
  "xaiTeamId": "your-team-id"
}
```

Then store your xAI management key in the Keychain:

```python
import keychain
keychain.set_api_key("xai", "mgmt_your_key_here")
```

Alternatively, you can use the legacy `team_id:key` format in the Keychain (e.g., `team123:mgmt_xxx`). If the Management API is unavailable, the app falls back to local log tracking.

## Local Tracking (Google)

For Google (which doesn't provide a billing API for API-key users), the app parses OpenClaw request logs from `~/.openclaw/logs/`. xAI also falls back to local tracking when the Management API is not configured. Log files should be JSONL format:

```json
{"timestamp": "2026-02-16T10:30:00Z", "model": "gemini-2.5-pro", "input_tokens": 1000000, "output_tokens": 200000}
{"timestamp": "2026-02-16T11:00:00Z", "model": "grok-3", "input_tokens": 500000, "output_tokens": 120000}
```

Cost is calculated using built-in per-model pricing tables.

## Running Tests

```bash
python3 -m pytest tests/ -v
```

## Building .app Bundle

```bash
pip install py2app
python3 setup.py py2app
```

The app bundle will be created in `dist/`.

## Project Structure

```
ai-budget-dashboard/
├── main.py              # Entry point, menu bar app (rumps)
├── config.py            # Budget limits, refresh interval
├── keychain.py          # macOS Keychain integration
├── notifier.py          # macOS notification alerts
├── tracker.py           # Local usage tracking (fallback)
├── providers/
│   ├── base.py          # Base provider + UsageData model
│   ├── anthropic_api.py # Anthropic Admin API
│   ├── openai_api.py    # OpenAI Costs API
│   ├── google_api.py    # Google — local tracking fallback
│   └── xai_api.py       # xAI — Management API + local fallback
├── tests/               # Test suite (123 tests)
├── requirements.txt
├── setup.py             # py2app bundling
└── pytest.ini
```
