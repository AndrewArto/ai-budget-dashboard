# AI Budget Dashboard — Specification

## Overview

macOS menu bar application that tracks AI API spending and remaining budget across four providers: **Anthropic (Claude)**, **OpenAI (GPT)**, **Google (Gemini)**, and **xAI (Grok)**. Displays real-time usage for the current calendar month with visual breakdown per provider.

## Problem

Running multiple AI models daily with no consolidated view of spend. Each provider has its own billing page with different UIs, different refresh rates, and no cross-provider summary. Need a single glance to see: how much spent, how much left, per provider, this month.

## Requirements

### Core

- **Menu bar icon** — sits in macOS status bar, shows total spend or remaining budget at a glance
- **Dropdown panel** — click to expand, shows per-provider breakdown:
  - Provider name + icon
  - Spent this month (USD)
  - Budget limit (configurable per provider)
  - Remaining budget
  - Progress bar (green → yellow → red as budget depletes)
  - Token count where available
- **Calendar month scope** — resets on the 1st of each month automatically
- **Auto-refresh** — polls provider APIs on configurable interval (default: every 15 min)
- **Manual refresh** — click to update now
- **Budget alerts** — system notification when a provider hits 80% and 95% of budget
- **Settings panel** — configure budget limits per provider, refresh interval, alert thresholds

### Provider APIs

| Provider | API Endpoint | Auth | Notes |
|----------|-------------|------|-------|
| Anthropic | `GET /v1/usage` (Admin API) | Admin API Key | Returns token counts + cost by model |
| OpenAI | `GET /v1/organization/costs` | Admin API Key | Returns daily cost breakdown |
| Google (Gemini) | Cloud Billing API or `generativelanguage` usage | Service Account / API Key | May need Cloud Billing export; free tier has no usage API — fallback to local tracking |
| xAI | `GET /v1/api-key` → rate limit headers | API Key | No dedicated billing API yet; track via rate limit headers or local request logging |

**Fallback strategy:** If a provider has no usage API (Gemini free tier, xAI), the app tracks usage locally by intercepting/logging OpenClaw's API calls. OpenClaw already logs all requests — parse those logs.

### Data Model

```
Provider {
  id: string              // "anthropic" | "openai" | "google" | "xai"
  name: string            // Display name
  apiKey: string          // Stored in macOS Keychain
  monthlyBudget: number   // USD, user-configured
  currentSpend: number    // USD, fetched or calculated
  tokensIn: number        // Input tokens this month
  tokensOut: number       // Output tokens this month
  lastUpdated: Date
}
```

### Menu Bar Display

Compact format in status bar:

```
$47.23 / $200    ← total spent / total budget
```

Or icon-only mode with colored dot:
- 🟢 under 60%
- 🟡 60-85%  
- 🔴 over 85%

### Dropdown Panel Layout

```
┌─────────────────────────────┐
│  AI Budget — February 2026  │
│                             │
│  Anthropic     $28.40/$80   │
│  ████████████░░░░  71%      │
│  1.2M in / 380K out         │
│                             │
│  OpenAI        $12.30/$60   │
│  ████████░░░░░░░░  41%      │
│  800K in / 210K out         │
│                             │
│  Google         $4.10/$30   │
│  ████░░░░░░░░░░░░  27%      │
│  2.1M in / 450K out         │
│                             │
│  xAI            $2.43/$30   │
│  ███░░░░░░░░░░░░░  16%      │
│  500K in / 120K out         │
│                             │
│  Total: $47.23 / $200       │
│  ─────────────────────────  │
│  ↻ Updated 2 min ago        │
│  ⚙ Settings                 │
└─────────────────────────────┘
```

## Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Framework | **Swift + SwiftUI** | Native macOS menu bar app, best integration with system UI, Keychain, notifications |
| Menu bar | `MenuBarExtra` (macOS 13+) | Native SwiftUI API for menu bar apps |
| HTTP | `URLSession` | Built-in, no dependencies |
| Storage | `UserDefaults` + Keychain | Settings in UserDefaults, API keys in Keychain |
| Notifications | `UNUserNotificationCenter` | Native macOS notifications |
| Build | Xcode / `swift build` | Standard toolchain |

**Alternative (if Swift is too heavy):** Electron + menubar npm package. Faster to build, cross-platform, but heavier on resources. Not recommended for a status bar widget.

**Alternative 2 (lightweight):** Python + rumps. Minimal menu bar app, ~200 lines. Good for MVP.

### Recommended: Python + rumps (MVP)

For speed of development and agent-friendliness:

```
ai-budget-dashboard/
├── main.py              # Entry point, menu bar app (rumps)
├── providers/
│   ├── __init__.py
│   ├── anthropic.py     # Anthropic usage API
│   ├── openai_api.py    # OpenAI billing API  
│   ├── google.py        # Google billing / local tracking
│   └── xai.py           # xAI usage / local tracking
├── config.py            # Budget limits, refresh interval
├── tracker.py           # Local usage tracking (fallback)
├── notifier.py          # macOS notifications
├── keychain.py          # macOS Keychain integration
├── requirements.txt     # rumps, requests, keyring
├── setup.py             # py2app for .app bundle
└── assets/
    └── icon.png         # Menu bar icon (16x16, template image)
```

After MVP works → optionally rewrite in Swift for native feel and lower resource usage.

## Configuration

Stored in `~/.config/ai-budget/config.json`:

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
  "localTrackingLogPath": "~/.openclaw/logs/"
}
```

API keys stored in macOS Keychain, not config file.

## Local Usage Tracking (Fallback)

For providers without billing APIs, parse OpenClaw request logs:

1. Read OpenClaw log files from `~/.openclaw/logs/`
2. Extract: timestamp, provider, model, tokens_in, tokens_out
3. Apply per-model pricing (hardcoded table, updated manually)
4. Aggregate by month

Pricing table example:
```python
PRICING = {
    "claude-opus-4": {"input": 15.0, "output": 75.0},      # per 1M tokens
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "gpt-4o": {"input": 2.50, "output": 10.0},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "grok-3": {"input": 3.0, "output": 15.0},
}
```

## Phases

### Phase 1 — MVP (2-3 days)

- Python + rumps menu bar app
- Config file with budget limits
- Anthropic + OpenAI usage APIs (both have working billing endpoints)
- Local tracking fallback for Google + xAI
- Basic dropdown with spend/budget per provider
- macOS notifications at thresholds

### Phase 2 — Polish (1-2 days)

- Keychain integration for API keys
- Settings UI (SwiftUI sheet or simple tkinter)
- Historical chart (last 7/30 days trend)
- py2app packaging → .app bundle
- Auto-start on login (LaunchAgent)

### Phase 3 — Native (optional)

- Rewrite in Swift/SwiftUI if resource usage or UX warrants it
- Widgets for macOS Notification Center

## Non-Goals

- No web UI (this is a local desktop tool)
- No multi-user / team tracking
- No invoice generation
- No per-conversation cost breakdown (just monthly totals)

## Open Questions

1. **Gemini billing API access** — verify if Gemini API returns usage data for API-key auth or requires Cloud Billing setup
2. **xAI usage endpoint** — check if xAI has added a usage/billing API (as of Feb 2026)
3. **OpenClaw log format** — confirm log structure for local tracking fallback
4. **Swift vs Python** — Andrey's preference for MVP speed vs native quality

## Success Criteria

- Single glance at menu bar shows total AI spend
- Per-provider breakdown in one click
- Alerts before budget overrun
- Works reliably on macOS (Apple Silicon)
- Under 50MB RAM, under 1% CPU
