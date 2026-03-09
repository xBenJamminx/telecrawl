# telecrawl

Telegram group memory layer with SQLite + FTS5 full-text search.

Give your AI agents full conversation memory on Telegram. Syncs complete chat history into a local SQLite database with instant full-text search.

## Why?

Discord has [discrawl](https://github.com/steipete/discrawl) — agents can search Discord history natively because Discord's Bot API supports it. Telegram's Bot API has **no method to read message history**. Bots can only see new messages via `getUpdates`, and that conflicts with any gateway already polling.

Telecrawl solves this by using [Telethon](https://github.com/LonamiWebs/Telethon) (Telegram's MTProto user API) to bypass the Bot API entirely. Full history access, zero conflicts, works alongside any bot framework.

## Features

- **Interactive init** — Discover and select chats to track, saves to `~/.telecrawl/config.toml`
- **Full history sync** — Fetches every message in a chat, not just new ones
- **Incremental sync** — After first sync, only fetches messages since last position
- **Rich message filtering** — Browse by author, time range, topic, with `--json` output
- **Real-time tail** — Background daemon captures messages as they arrive
- **Full-text search** — SQLite FTS5 with BM25 relevance ranking
- **FTS5 query sanitization** — Handles URLs, hyphens, and special characters cleanly
- **TOML config** — No more passing `--chat-id` every time
- **JSON output** — `--json` flag on every command for piping to other tools
- **Headless auth** — Two-step authentication for servers without interactive terminals
- **Systemd ready** — Runs as a background service for continuous capture

## Installation

```bash
git clone https://github.com/xBenJamminx/telecrawl.git
cd telecrawl
pip install -e .
```

## Setup

### 1. Get Telegram API Credentials

1. Go to [my.telegram.org/apps](https://my.telegram.org/apps)
2. Create an application
3. Copy your `api_id` and `api_hash`

### 2. Configure Environment

Create a `.env` file:

```bash
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
```

### 3. Authenticate

Telecrawl authenticates as your user account (not a bot). On headless servers, use the two-step auth:

```bash
# Step 1: Request verification code
python -m telecrawl.auth request +1XXXXXXXXXX

# Step 2: Enter the code sent to your Telegram
python -m telecrawl.auth verify 12345
```

Session persists after first auth — no need to re-authenticate.

### 4. Initialize Config

Discover your chats and select which ones to track:

```bash
telecrawl init
```

This connects to Telegram, lists all your groups/channels, and lets you pick which to track. Saves config to `~/.telecrawl/config.toml`. After init, you never need `--chat-id` again.

## Usage

### Sync Messages

```bash
# Sync all configured chats (after running init)
telecrawl sync --full -v

# Sync specific chat (overrides config)
telecrawl sync --chat-id -1001234567890

# Incremental sync (only new messages since last sync)
telecrawl sync
```

### Search Messages

```bash
# Basic search
telecrawl search "python programming"

# Search in specific chat
telecrawl search "deployment" --chat-id -1001234567890

# Limit results
telecrawl search "bug fix" -l 10
```

### Browse Messages

Rich filtering for browsing history:

```bash
# Last 24 hours
telecrawl messages --hours 24

# By author
telecrawl messages --author john --days 7

# By forum topic
telecrawl messages --topic 42 --last 20

# Since a specific date, oldest first
telecrawl messages --since 2025-01-15 --oldest

# JSON output (pipe to jq, feed to agents, etc.)
telecrawl messages --hours 6 --json
```

### Real-Time Tail

Capture messages as they arrive (runs continuously):

```bash
telecrawl tail
```

### View Recent Messages

```bash
telecrawl recent --limit 20
telecrawl recent --chat-id -1001234567890
```

### JSON Output

Every command supports `--json` for machine-readable output:

```bash
telecrawl search "deployment" --json
telecrawl stats --json
telecrawl messages --author ben --days 3 --json | jq '.[] | .text'
```

### Database Status

```bash
# Overview
telecrawl status

# Statistics
telecrawl stats

# Health check
telecrawl doctor
```

## Running as a Service

Create a systemd service for continuous message capture:

```ini
[Unit]
Description=Telecrawl - Telegram message archiver
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/your/project
ExecStart=/usr/bin/python3 -m telecrawl tail --chat-id YOUR_CHAT_ID
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/path/to/your/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable telecrawl
sudo systemctl start telecrawl
```

## Python API

```python
import asyncio
from telethon import TelegramClient
from telecrawl.db import TeleCrawlDB
from telecrawl.sync import TelegramSyncer
from telecrawl.query import TeleCrawlQuery

async def main():
    # Connect
    client = TelegramClient('session', api_id, api_hash)
    await client.start()

    db = TeleCrawlDB("telecrawl.db")
    db.connect()

    # Sync
    syncer = TelegramSyncer(client, db)
    count = await syncer.sync_chat(-1001234567890, verbose=True)
    print(f"Synced {count} messages")

    # Search
    query = TeleCrawlQuery(db)
    results = query.search("deployment issue", limit=10)
    for r in results:
        print(f"{r['sender']}: {r['text']}")

    db.close()
    await client.disconnect()

asyncio.run(main())
```

## How It Works

1. **Telethon (MTProto)** — Authenticates as a user account, giving full access to `iter_messages()` which returns complete chat history. This is the key difference from Bot API approaches.
2. **Incremental sync** — Tracks last synced message ID per chat via `min_id` parameter. Only fetches newer messages on subsequent syncs.
3. **FTS5 index** — Automatically maintained via SQLite triggers. Updated on every insert.
4. **BM25 ranking** — Search results ranked by relevance, not just recency.
5. **Query sanitization** — Special characters (dots in URLs, hyphens, slashes) are automatically quoted to prevent FTS5 syntax errors.

## Database Schema

| Column | Type | Description |
|--------|------|-------------|
| message_id | INTEGER | Primary key (Telegram message ID) |
| chat_id | INTEGER | Telegram chat ID |
| topic_id | INTEGER | Topic/thread ID (for forum groups) |
| sender_id | INTEGER | User ID of sender |
| sender_username | TEXT | Sender's @username |
| sender_first_name | TEXT | Sender's first name |
| sender_last_name | TEXT | Sender's last name |
| text | TEXT | Message text content |
| timestamp | INTEGER | Unix timestamp of message |
| created_at | INTEGER | Unix timestamp when synced |

## Limitations

- Text messages only (no media sync yet)
- Requires user account authentication (not bot-only)
- Telegram rate limits apply (Telethon handles backoff automatically)

## License

MIT

## Credits

Inspired by [discrawl](https://github.com/steipete/discrawl) by Peter Steinberger.

Discrawl gave Discord agents memory. Telegram had nothing — so telecrawl was built.
