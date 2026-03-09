"""
Command-line interface for telecrawl.
"""

import asyncio
import json
import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

from .db import TeleCrawlDB
from .query import TeleCrawlQuery
from .config import (
    get_db_path, get_session_path, get_configured_chat_ids,
    get_configured_chats, config_exists, load_config as load_toml_config,
    save_config, format_chat_type, CONFIG_PATH,
    DEFAULT_DB, DEFAULT_SESSION,
)


def load_credentials():
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
    api_id, api_hash = load_credentials()
    return TelegramClient(session_path, api_id, api_hash)


def resolve_chat_ids(args) -> list:
    """
    Resolve chat IDs from CLI --chat-id flag or config file.
    Returns list of int chat IDs, or exits with error if none found.
    """
    if hasattr(args, 'chat_id') and args.chat_id:
        return [int(cid.strip()) for cid in args.chat_id.split(',')]

    configured = get_configured_chat_ids()
    if configured:
        return configured

    print("Error: No --chat-id provided and no chats configured.")
    print("Run 'telecrawl init' to configure tracked chats,")
    print("or pass --chat-id explicitly.")
    sys.exit(1)


def cmd_init(args):
    """Initialize telecrawl config by discovering and selecting chats."""
    from telethon.tl.types import Channel, Chat, User

    session_path = get_session_path(args.session)

    # Check for existing config
    if config_exists():
        existing = load_toml_config()
        existing_chats = existing.get('chats', [])
        print(f"Existing config found at {CONFIG_PATH}")
        print(f"Currently tracking {len(existing_chats)} chat(s):")
        for chat in existing_chats:
            print(f"  [{chat['type']}] {chat['name']} ({chat['id']})")
        print()
        answer = input("Overwrite config? [y/N] ").strip().lower()
        if answer not in ('y', 'yes'):
            print("Aborted.")
            return

    client = get_client(session_path)

    async def _init():
        await client.start()
        me = await client.get_me()
        print(f"Authenticated as {me.first_name} (@{me.username})")
        print("\nDiscovering chats...\n")

        dialogs = []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity

            # Skip individual users / saved messages / bots
            if isinstance(entity, User):
                continue

            chat_type = format_chat_type(entity)
            member_count = getattr(entity, 'participants_count', None)

            dialogs.append({
                'id': dialog.id,
                'name': dialog.name or '(unnamed)',
                'type': chat_type,
                'member_count': member_count,
            })

        if not dialogs:
            print("No groups, supergroups, or channels found.")
            await client.disconnect()
            return

        # Print numbered list
        print(f"Found {len(dialogs)} chat(s):\n")
        print(f"  {'#':>4}  {'Type':<12} {'Members':>8}  Name")
        print(f"  {'':->4}  {'':->12} {'':->8}  {'':->30}")

        for i, d in enumerate(dialogs, 1):
            members_str = str(d['member_count']) if d['member_count'] else '-'
            print(f"  {i:>4}  {d['type']:<12} {members_str:>8}  {d['name']}")

        print(f"\nSelect chats to track.")
        print(f"Enter numbers separated by commas (e.g. 1,3,5), or 'all'.")
        selection = input("> ").strip()

        if not selection:
            print("No selection made. Aborted.")
            await client.disconnect()
            return

        if selection.lower() == 'all':
            selected = dialogs
        else:
            try:
                indices = [int(s.strip()) for s in selection.split(',')]
                selected = []
                for idx in indices:
                    if 1 <= idx <= len(dialogs):
                        selected.append(dialogs[idx - 1])
                    else:
                        print(f"Warning: skipping invalid index {idx}")
            except ValueError:
                print("Error: invalid input. Enter comma-separated numbers or 'all'.")
                await client.disconnect()
                return

        if not selected:
            print("No valid chats selected. Aborted.")
            await client.disconnect()
            return

        # Build config
        db_path = get_db_path(args.db)
        sess_path = get_session_path(args.session)

        config = {
            'telecrawl': {
                'db_path': db_path,
                'session_path': sess_path,
            },
            'chats': [
                {
                    'id': chat['id'],
                    'name': chat['name'],
                    'type': chat['type'],
                }
                for chat in selected
            ],
        }

        saved_path = save_config(config)
        print(f"\nConfig saved to {saved_path}")
        print(f"Tracking {len(selected)} chat(s):")
        for chat in selected:
            print(f"  [{chat['type']}] {chat['name']} ({chat['id']})")

        print(f"\nYou can now run 'telecrawl sync' without --chat-id.")

        await client.disconnect()

    asyncio.run(_init())


def cmd_sync(args):
    """Sync messages from Telegram via Telethon."""
    from .sync import TelegramSyncer

    db_path = get_db_path(args.db)
    session_path = get_session_path(args.session)

    client = get_client(session_path)
    db = TeleCrawlDB(db_path)
    db.connect()

    async def _sync():
        await client.start()
        syncer = TelegramSyncer(client, db)

        chat_ids = resolve_chat_ids(args)

        if not args.chat_id and len(chat_ids) > 0:
            chats = get_configured_chats()
            names = {c['id']: c['name'] for c in chats}
            print(f"Syncing {len(chat_ids)} configured chat(s):")
            for cid in chat_ids:
                name = names.get(cid, str(cid))
                print(f"  {name} ({cid})")
            print()

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

    api_id, api_hash = load_credentials()
    session_path = get_session_path(args.session)
    db_path = get_db_path(args.db)

    if args.chat_id:
        chat_id = int(args.chat_id)
    else:
        configured = get_configured_chat_ids()
        if configured:
            chat_id = configured[0]
            chats = get_configured_chats()
            names = {c['id']: c['name'] for c in chats}
            name = names.get(chat_id, str(chat_id))
            print(f"No --chat-id provided, using first configured chat:")
            print(f"  {name} ({chat_id})\n")
        else:
            print("Error: No --chat-id provided and no chats configured.")
            print("Run 'telecrawl init' to configure tracked chats,")
            print("or pass --chat-id explicitly.")
            sys.exit(1)

    asyncio.run(run_tail(
        api_id=api_id,
        api_hash=api_hash,
        session_path=session_path,
        chat_id=chat_id,
        db_path=db_path,
    ))


def cmd_search(args):
    """Search messages."""
    db = TeleCrawlDB(get_db_path(args.db))
    db.connect()

    query_engine = TeleCrawlQuery(db)

    results = query_engine.search(
        args.query,
        chat_id=args.chat_id,
        limit=args.limit
    )

    if getattr(args, 'json', False):
        print(json.dumps(results, indent=2))
    elif not results:
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
    db = TeleCrawlDB(get_db_path(args.db))
    db.connect()

    query_engine = TeleCrawlQuery(db)
    results = query_engine.get_recent(chat_id=args.chat_id, limit=args.limit)

    if getattr(args, 'json', False):
        print(json.dumps(results, indent=2))
    elif not results:
        print("No messages found")
    else:
        print(f"\nRecent {len(results)} messages:\n")
        for result in results:
            print(f"[{result['message_id']}] {result['sender']} @ {result['timestamp']}")
            print(f"   {result['text'][:200]}\n")

    db.close()


def cmd_messages(args):
    """Browse messages with rich filtering."""
    db = TeleCrawlDB(get_db_path(args.db))
    db.connect()

    query_engine = TeleCrawlQuery(db)

    # Resolve time filters to a unix timestamp
    since = None
    if args.since:
        try:
            since = datetime.strptime(args.since, '%Y-%m-%d').timestamp()
        except ValueError:
            try:
                since = datetime.strptime(args.since, '%Y-%m-%dT%H:%M:%S').timestamp()
            except ValueError:
                print(f"Error: invalid date format '{args.since}'. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")
                sys.exit(1)
    elif args.days:
        since = (datetime.now() - timedelta(days=args.days)).timestamp()
    elif args.hours:
        since = (datetime.now() - timedelta(hours=args.hours)).timestamp()

    limit = args.last if args.last else args.limit

    results = query_engine.get_messages(
        chat_id=args.chat_id,
        sender=args.author,
        topic_id=args.topic,
        since=since,
        limit=limit,
        oldest_first=args.oldest,
    )

    if getattr(args, 'json', False):
        print(json.dumps(results, indent=2))
    elif not results:
        print("No messages found")
    else:
        print(f"\n{len(results)} messages:\n")
        for msg in results:
            topic_str = f" [topic:{msg['topic_id']}]" if msg.get('topic_id') else ""
            print(f"[{msg['message_id']}] {msg['sender']} @ {msg['timestamp']}{topic_str}")
            text = msg.get('text') or ''
            print(f"   {text[:200]}\n")

    db.close()


def cmd_stats(args):
    """Show database statistics."""
    db = TeleCrawlDB(get_db_path(args.db))
    db.connect()

    query_engine = TeleCrawlQuery(db)
    stats = query_engine.get_stats()

    if getattr(args, 'json', False):
        print(json.dumps(stats, indent=2))
    else:
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
    db = TeleCrawlDB(get_db_path(args.db))
    db.connect()

    query_engine = TeleCrawlQuery(db)
    health = query_engine.verify()

    if getattr(args, 'json', False):
        print(json.dumps(health, indent=2))
    else:
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
    db = TeleCrawlDB(get_db_path(args.db))
    db.connect()

    query_engine = TeleCrawlQuery(db)
    stats = query_engine.get_stats()

    cursor = db.conn.cursor()
    date_range = cursor.execute("""
        SELECT MIN(timestamp), MAX(timestamp) FROM messages
    """).fetchone()

    sync_info = cursor.execute("""
        SELECT chat_id, last_sync_at FROM sync_state
        ORDER BY last_sync_at DESC LIMIT 3
    """).fetchall()

    if getattr(args, 'json', False):
        status_data = {
            'total_messages': stats['total_messages'],
            'total_chats': stats['total_chats'],
            'oldest_message': date_range[0],
            'newest_message': date_range[1],
            'days_of_history': None,
            'top_chats': stats['chats'][:5],
            'recent_syncs': [dict(row) for row in sync_info],
        }
        if date_range[0] and date_range[1]:
            oldest = datetime.fromtimestamp(date_range[0])
            newest = datetime.fromtimestamp(date_range[1])
            status_data['days_of_history'] = (newest - oldest).days
        print(json.dumps(status_data, indent=2))
    else:
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

        if sync_info:
            print("\n  Recent syncs:")
            for row in sync_info:
                sync_time = datetime.fromtimestamp(row['last_sync_at'])
                print(f"    #{row['chat_id']}: {sync_time.strftime('%Y-%m-%d %H:%M')}")

        # Show configured chats if config exists
        configured = get_configured_chats()
        if configured:
            print(f"\n  Configured chats ({len(configured)}):")
            for chat in configured:
                print(f"    [{chat['type']}] {chat['name']} ({chat['id']})")

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
    parser.add_argument('--json', action='store_true', default=False, help='Output JSON instead of formatted text')

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Init command
    subparsers.add_parser('init', help='Discover chats and create config')

    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Sync messages from Telegram')
    sync_parser.add_argument('--chat-id', help='Telegram chat ID(s), comma-separated (default: from config)')
    sync_parser.add_argument('--full', action='store_true', help='Full resync (ignore last position)')
    sync_parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    # Tail command
    tail_parser = subparsers.add_parser('tail', help='Real-time message listener')
    tail_parser.add_argument('--chat-id', help='Telegram chat ID to monitor (default: first from config)')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search messages')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--chat-id', type=int, help='Filter by chat ID')
    search_parser.add_argument('-l', '--limit', type=int, default=50, help='Max results (default: 50)')

    # Recent command
    recent_parser = subparsers.add_parser('recent', help='Show recent messages')
    recent_parser.add_argument('--chat-id', type=int, help='Filter by chat ID')
    recent_parser.add_argument('-l', '--limit', type=int, default=50, help='Max results (default: 50)')

    # Messages command
    msg_parser = subparsers.add_parser('messages', help='Browse messages with rich filtering')
    msg_parser.add_argument('--chat-id', type=int, help='Filter by chat ID')
    msg_parser.add_argument('--author', type=str, help='Filter by username or first name (case-insensitive)')
    msg_parser.add_argument('--topic', type=int, help='Filter by forum topic ID')
    msg_parser.add_argument('--since', type=str, help='Messages since date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)')
    msg_parser.add_argument('--days', type=float, help='Messages from the last N days')
    msg_parser.add_argument('--hours', type=float, help='Messages from the last N hours')
    msg_parser.add_argument('--last', type=int, help='Return last N messages (overrides --limit)')
    msg_parser.add_argument('-l', '--limit', type=int, default=50, help='Max results (default: 50)')
    msg_parser.add_argument('--oldest', action='store_true', help='Chronological order (oldest first)')

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
        'init': cmd_init,
        'sync': cmd_sync,
        'tail': cmd_tail,
        'search': cmd_search,
        'recent': cmd_recent,
        'messages': cmd_messages,
        'stats': cmd_stats,
        'status': cmd_status,
        'doctor': cmd_doctor,
    }

    commands[args.command](args)


if __name__ == '__main__':
    main()
