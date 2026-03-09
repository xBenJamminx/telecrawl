"""
Command-line interface for telecrawl.
"""

import asyncio
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

from .db import TeleCrawlDB
from .query import TeleCrawlQuery


DEFAULT_DB = str(Path.home() / '.telecrawl' / 'telecrawl.db')
DEFAULT_SESSION = str(Path.home() / '.telecrawl' / 'telecrawl')


def load_config():
    """Load Telethon credentials from environment."""
    # Look for .env in current directory or parent
    env_path = Path.cwd() / '.env'
    if not env_path.exists():
        env_path = Path.cwd().parent / '.env'

    if env_path.exists():
        load_dotenv(env_path)

    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')

    if not api_id or not api_hash:
        print("Error: TELEGRAM_API_ID and TELEGRAM_API_HASH not found")
        print("Get these from https://my.telegram.org/apps")
        print("Set them in a .env file or as environment variables")
        sys.exit(1)

    return int(api_id), api_hash


def get_client(session_path: str = DEFAULT_SESSION):
    """Create a Telethon client."""
    from telethon import TelegramClient
    api_id, api_hash = load_config()
    return TelegramClient(session_path, api_id, api_hash)


def cmd_sync(args):
    """Sync messages from Telegram via Telethon."""
    from .sync import TelegramSyncer

    client = get_client(args.session)
    db = TeleCrawlDB(args.db)
    db.connect()

    async def _sync():
        await client.start()
        syncer = TelegramSyncer(client, db)

        if args.chat_id:
            chat_ids = [int(cid.strip()) for cid in args.chat_id.split(',')]
        else:
            print("Error: --chat-id is required")
            sys.exit(1)

        results = await syncer.sync_multiple_chats(
            chat_ids, full=args.full, verbose=args.verbose
        )

        total = sum(results.values())
        print(f"\nSync complete: {total} new messages")

        await client.disconnect()

    asyncio.run(_sync())
    db.close()


def cmd_tail(args):
    """Start real-time message listener."""
    from .tail import run_tail

    api_id, api_hash = load_config()

    if not args.chat_id:
        print("Error: --chat-id is required")
        sys.exit(1)

    asyncio.run(run_tail(
        api_id=api_id,
        api_hash=api_hash,
        session_path=args.session,
        chat_id=int(args.chat_id),
        db_path=args.db,
    ))


def cmd_search(args):
    """Search messages."""
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
    """Show recent messages."""
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
    """Show database statistics."""
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
    """Verify database integrity."""
    db = TeleCrawlDB(args.db)
    db.connect()

    query_engine = TeleCrawlQuery(db)
    health = query_engine.verify()

    print(f"\nDatabase Health Check:")
    print(f"  Messages: {health['messages_count']}")
    print(f"  FTS entries: {health['fts_count']}")
    print(f"  Orphaned FTS: {health['orphaned_fts']}")
    print(f"  Missing FTS: {health['missing_fts']}")
    print(f"\n  Status: {'HEALTHY' if health['healthy'] else 'ISSUES DETECTED'}")

    if not health['healthy']:
        print("\nRun 'telecrawl doctor --rebuild-fts' to rebuild FTS index")

    db.close()


def cmd_status(args):
    """Show live status overview."""
    from datetime import datetime

    db = TeleCrawlDB(args.db)
    db.connect()

    query_engine = TeleCrawlQuery(db)
    stats = query_engine.get_stats()

    cursor = db.conn.cursor()
    date_range = cursor.execute("""
        SELECT MIN(timestamp), MAX(timestamp) FROM messages
    """).fetchone()

    print("\n" + "=" * 50)
    print("  telecrawl - status".center(50))
    print("=" * 50)

    print(f"\n  {stats['total_messages']:,} messages archived")
    print(f"  {stats['total_chats']:,} chats indexed")

    if date_range[0] and date_range[1]:
        oldest = datetime.fromtimestamp(date_range[0])
        newest = datetime.fromtimestamp(date_range[1])
        days_span = (newest - oldest).days
        print(f"  {days_span:,} days of history")
        print(f"\n  Last message: {newest.strftime('%Y-%m-%d %H:%M')}")

    if stats['chats']:
        print("\n  Top chats:")
        for chat in stats['chats'][:5]:
            print(f"    #{chat['chat_id']}: {chat['message_count']:,} msgs")

    sync_info = cursor.execute("""
        SELECT chat_id, last_sync_at FROM sync_state
        ORDER BY last_sync_at DESC LIMIT 3
    """).fetchall()

    if sync_info:
        print("\n  Recent syncs:")
        for row in sync_info:
            sync_time = datetime.fromtimestamp(row['last_sync_at'])
            print(f"    #{row['chat_id']}: {sync_time.strftime('%Y-%m-%d %H:%M')}")

    print("\n" + "=" * 50)
    print("  Database ready".center(50))
    print("=" * 50 + "\n")

    db.close()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='telecrawl: Telegram group memory with full-text search'
    )
    parser.add_argument('--db', default=DEFAULT_DB, help=f'Database path (default: {DEFAULT_DB})')
    parser.add_argument('--session', default=DEFAULT_SESSION, help=f'Telethon session path (default: {DEFAULT_SESSION})')

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Sync messages from Telegram')
    sync_parser.add_argument('--chat-id', required=True, help='Telegram chat ID(s), comma-separated')
    sync_parser.add_argument('--full', action='store_true', help='Full resync (ignore last position)')
    sync_parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    # Tail command
    tail_parser = subparsers.add_parser('tail', help='Real-time message listener')
    tail_parser.add_argument('--chat-id', required=True, help='Telegram chat ID to monitor')

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
    subparsers.add_parser('stats', help='Show database statistics')

    # Status command
    subparsers.add_parser('status', help='Show live status overview')

    # Doctor command
    subparsers.add_parser('doctor', help='Verify database integrity')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        'sync': cmd_sync,
        'tail': cmd_tail,
        'search': cmd_search,
        'recent': cmd_recent,
        'stats': cmd_stats,
        'status': cmd_status,
        'doctor': cmd_doctor,
    }

    commands[args.command](args)


if __name__ == '__main__':
    main()
