"""
Command-line interface for telecrawl
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List
from dotenv import load_dotenv

from .db import TeleCrawlDB
from .sync import TelegramSyncer
from .query import TeleCrawlQuery


def load_config():
    """Load configuration from .env"""
    # Look for .env in current directory or parent
    env_path = Path.cwd() / '.env'
    if not env_path.exists():
        env_path = Path.cwd().parent / '.env'

    if env_path.exists():
        load_dotenv(env_path)

    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN not found in environment")
        print("Create a .env file with: TELEGRAM_BOT_TOKEN=your_token_here")
        sys.exit(1)

    return bot_token


def cmd_sync(args):
    """Sync messages from Telegram"""
    bot_token = load_config()

    db = TeleCrawlDB(args.db)
    db.connect()

    syncer = TelegramSyncer(bot_token, db)

    if args.chat_id:
        chat_ids = [int(cid.strip()) for cid in args.chat_id.split(',')]
    else:
        print("Error: --chat-id is required")
        sys.exit(1)

    results = syncer.sync_multiple_chats(chat_ids, verbose=args.verbose)

    total = sum(results.values())
    print(f"\nSync complete: {total} new messages")

    db.close()


def cmd_search(args):
    """Search messages"""
    db = TeleCrawlDB(args.db)
    db.connect()

    query_engine = TeleCrawlQuery(db)

    results = query_engine.search(
        args.query,
        chat_id=args.chat_id,
        limit=args.limit
    )

    if not results:
        print("No results found")
    else:
        print(f"\nFound {len(results)} results:\n")
        for i, result in enumerate(results, 1):
            print(f"{i}. [{result['message_id']}] {result['sender']} @ {result['timestamp']}")
            print(f"   {result['text'][:200]}")
            print(f"   Relevance: {result['relevance']:.2f}\n")

    db.close()


def cmd_recent(args):
    """Show recent messages"""
    db = TeleCrawlDB(args.db)
    db.connect()

    query_engine = TeleCrawlQuery(db)
    results = query_engine.get_recent(chat_id=args.chat_id, limit=args.limit)

    if not results:
        print("No messages found")
    else:
        print(f"\nRecent {len(results)} messages:\n")
        for result in results:
            print(f"[{result['message_id']}] {result['sender']} @ {result['timestamp']}")
            print(f"   {result['text'][:200]}\n")

    db.close()


def cmd_stats(args):
    """Show database statistics"""
    db = TeleCrawlDB(args.db)
    db.connect()

    query_engine = TeleCrawlQuery(db)
    stats = query_engine.get_stats()

    print(f"\nDatabase Statistics:")
    print(f"  Total messages: {stats['total_messages']}")
    print(f"  Total chats: {stats['total_chats']}\n")

    if stats['chats']:
        print("Messages per chat:")
        for chat in stats['chats']:
            print(f"  Chat {chat['chat_id']}: {chat['message_count']} messages")

    db.close()


def cmd_doctor(args):
    """Verify database integrity"""
    db = TeleCrawlDB(args.db)
    db.connect()

    query_engine = TeleCrawlQuery(db)
    health = query_engine.verify()

    print(f"\nDatabase Health Check:")
    print(f"  Messages: {health['messages_count']}")
    print(f"  FTS entries: {health['fts_count']}")
    print(f"  Orphaned FTS: {health['orphaned_fts']}")
    print(f"  Missing FTS: {health['missing_fts']}")
    print(f"\n  Status: {'✓ HEALTHY' if health['healthy'] else '✗ ISSUES DETECTED'}")

    if not health['healthy']:
        print("\nRun 'telecrawl doctor --rebuild-fts' to rebuild FTS index")

    db.close()


def cmd_status(args):
    """Show live status like discrawl"""
    from datetime import datetime

    db = TeleCrawlDB(args.db)
    db.connect()

    query_engine = TeleCrawlQuery(db)
    stats = query_engine.get_stats()

    # Calculate date range
    cursor = db.conn.cursor()
    date_range = cursor.execute("""
        SELECT MIN(timestamp), MAX(timestamp) FROM messages
    """).fetchone()

    print("\n" + "═" * 50)
    print("  📊 telecrawl — live".center(50))
    print("═" * 50)

    print(f"\n  🗂️  {stats['total_messages']:,} messages archived")
    print(f"  💬 {stats['total_chats']:,} chats indexed")

    if date_range[0] and date_range[1]:
        from datetime import datetime
        oldest = datetime.fromtimestamp(date_range[0])
        newest = datetime.fromtimestamp(date_range[1])
        days_span = (newest - oldest).days
        print(f"  📅 {days_span:,} days of history")
        print(f"\n  🕐 Last message: {newest.strftime('%Y-%m-%d %H:%M')}")

    if stats['chats']:
        print("\n  ┌─ Top chats")
        for chat in stats['chats'][:5]:
            print(f"  │  #{chat['chat_id']}: {chat['message_count']:,} msgs")

    # Get last sync info
    sync_info = cursor.execute("""
        SELECT chat_id, last_sync_at FROM sync_state
        ORDER BY last_sync_at DESC LIMIT 3
    """).fetchall()

    if sync_info:
        print("\n  ┌─ Recent syncs")
        for row in sync_info:
            sync_time = datetime.fromtimestamp(row['last_sync_at'])
            print(f"  │  #{row['chat_id']}: {sync_time.strftime('%Y-%m-%d %H:%M')}")

    print("\n" + "═" * 50)
    print("  ✓ Database ready".center(50))
    print("═" * 50 + "\n")

    db.close()


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='telecrawl: Telegram group memory with full-text search'
    )
    parser.add_argument('--db', default='telecrawl.db', help='Database path (default: telecrawl.db)')

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Sync messages from Telegram')
    sync_parser.add_argument('--chat-id', required=True, help='Telegram chat ID(s), comma-separated')
    sync_parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search messages')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--chat-id', type=int, help='Filter by chat ID')
    search_parser.add_argument('-l', '--limit', type=int, default=50, help='Max results (default: 50)')

    # Recent command
    recent_parser = subparsers.add_parser('recent', help='Show recent messages')
    recent_parser.add_argument('--chat-id', type=int, help='Filter by chat ID')
    recent_parser.add_argument('-l', '--limit', type=int, default=50, help='Max results (default: 50)')

    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show database statistics')

    # Status command
    status_parser = subparsers.add_parser('status', help='Show live status overview')

    # Doctor command
    doctor_parser = subparsers.add_parser('doctor', help='Verify database integrity')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        'sync': cmd_sync,
        'search': cmd_search,
        'recent': cmd_recent,
        'stats': cmd_stats,
        'status': cmd_status,
        'doctor': cmd_doctor
    }

    commands[args.command](args)


if __name__ == '__main__':
    main()
