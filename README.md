# telecrawl

Telegram group memory layer with SQLite + FTS5 full-text search.

Mirror your Telegram group messages to a local SQLite database with powerful full-text search capabilities. Similar to discrawl but for Telegram.

## Features

- 🔄 **Incremental sync** — Only fetch new messages since last sync
- 🔍 **Full-text search** — SQLite FTS5 with BM25 ranking
- 📊 **Statistics** — View message counts, activity per chat
- 🏥 **Health checks** — Verify database integrity
- 🚀 **Simple CLI** — Easy to use command-line interface

## Installation

```bash
git clone https://github.com/yourusername/telecrawl.git
cd telecrawl
pip install -e .
```

Or install from PyPI:

```bash
pip install telecrawl
```

## Setup

### 1. Create a Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token (looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
4. Add your bot to the group(s) you want to monitor

### 2. Get Chat IDs

To find your chat ID, you can:
- Forward a message from the group to [@userinfobot](https://t.me/userinfobot)
- Or use the bot's `getUpdates` endpoint after adding it to the group

### 3. Configure Environment

Create a `.env` file:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

## Usage

### Sync Messages

Sync messages from one or more chats:

```bash
# Sync a single chat
telecrawl sync --chat-id -1001234567890

# Sync multiple chats
telecrawl sync --chat-id -1001234567890,-1009876543210

# Verbose output
telecrawl sync --chat-id -1001234567890 -v
```

### Search Messages

Search across all synced messages:

```bash
# Basic search
telecrawl search "python programming"

# Search in specific chat
telecrawl search "python" --chat-id -1001234567890

# Limit results
telecrawl search "python" --limit 10
```

### View Recent Messages

```bash
# Show recent messages across all chats
telecrawl recent

# Recent from specific chat
telecrawl recent --chat-id -1001234567890

# Limit results
telecrawl recent --limit 20
```

### Database Statistics

```bash
telecrawl stats
```

### Health Check

Verify database integrity:

```bash
telecrawl doctor
```

## Database Schema

### Messages Table

| Column | Type | Description |
|--------|------|-------------|
| message_id | INTEGER | Primary key, Telegram message ID |
| chat_id | INTEGER | Telegram chat ID |
| topic_id | INTEGER | Topic/thread ID (for forum groups) |
| sender_id | INTEGER | User ID of sender |
| sender_username | TEXT | Sender's username |
| sender_first_name | TEXT | Sender's first name |
| sender_last_name | TEXT | Sender's last name |
| text | TEXT | Message text content |
| timestamp | INTEGER | Unix timestamp of message |
| created_at | INTEGER | Unix timestamp when synced |

### FTS5 Search

The `messages_fts` virtual table enables full-text search across:
- Message text
- Sender username
- Sender first name
- Sender last name

Search results are ranked using BM25 algorithm.

## Python API

Use telecrawl programmatically:

```python
from telecrawl.db import TeleCrawlDB
from telecrawl.sync import TelegramSyncer
from telecrawl.query import TeleCrawlQuery

# Initialize
db = TeleCrawlDB("telecrawl.db")
db.connect()

# Sync messages
syncer = TelegramSyncer("your_bot_token", db)
new_messages = syncer.sync_chat(-1001234567890, verbose=True)

# Search
query_engine = TeleCrawlQuery(db)
results = query_engine.search("python programming", limit=10)

for result in results:
    print(f"{result['sender']}: {result['text']}")

# Stats
stats = query_engine.get_stats()
print(f"Total messages: {stats['total_messages']}")

# Cleanup
db.close()
```

## Advanced Usage

### Custom Database Location

```bash
telecrawl --db /path/to/custom.db sync --chat-id -1001234567890
```

### Incremental Sync Pattern

Set up a cron job for continuous sync:

```bash
*/15 * * * * cd /path/to/telecrawl && telecrawl sync --chat-id -1001234567890
```

This syncs every 15 minutes. Only new messages are fetched.

## How It Works

1. **First Sync**: Fetches all available messages from Telegram Bot API
2. **Incremental Sync**: Tracks last synced message ID per chat, only fetches newer messages
3. **FTS5 Index**: Automatically updated via SQLite triggers when messages are inserted
4. **BM25 Ranking**: Search results ranked by relevance using BM25 algorithm

## Limitations

- Bot must be a member of the group to see messages
- Bot API only provides messages sent after the bot was added
- Rate limits apply (Telegram Bot API allows ~30 requests/second)
- Text-only messages (no media sync yet)

## Troubleshooting

### No messages syncing

- Verify bot is added to the group
- Check bot token is correct
- Ensure chat ID is correct (negative for groups)
- Bot needs to remain in the group to sync

### FTS5 errors

Run the doctor command:

```bash
telecrawl doctor
```

## License

MIT

## Contributing

PRs welcome! Please open an issue first to discuss changes.

## Credits

Built by Cortana 💜

Inspired by discrawl for Discord.
