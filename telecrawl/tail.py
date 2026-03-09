"""
Real-time Telegram message listener via Telethon.
Captures messages as they arrive and inserts into SQLite.
Designed to run as a background daemon (systemd service).
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Optional

from telethon import TelegramClient, events
from telethon.tl.types import Message

from .db import TeleCrawlDB


async def run_tail(api_id: int, api_hash: str, session_path: str,
                   chat_id: int, db_path: str):
    """
    Start real-time message listener for a Telegram chat.

    Args:
        api_id: Telegram API ID from my.telegram.org
        api_hash: Telegram API hash from my.telegram.org
        session_path: Path to Telethon .session file
        chat_id: Telegram chat/group ID to monitor
        db_path: Path to SQLite database
    """
    db = TeleCrawlDB(db_path)
    db.connect()

    client = TelegramClient(session_path, api_id, api_hash)
    await client.start()

    entity = await client.get_entity(chat_id)
    print(f"[telecrawl tail] Listening on chat {chat_id}...")
    print(f"[telecrawl tail] Database: {db_path}")

    @client.on(events.NewMessage(chats=entity))
    async def handler(event):
        message = event.message
        if not isinstance(message, Message):
            return

        text = message.text or message.message
        if not text:
            return

        sender = await message.get_sender()
        msg_data = {
            'message_id': message.id,
            'chat_id': chat_id,
            'topic_id': getattr(message, 'reply_to', None) and getattr(message.reply_to, 'forum_topic', False) and message.reply_to.reply_to_msg_id,
            'sender_id': sender.id if sender else None,
            'sender_username': getattr(sender, 'username', None),
            'sender_first_name': getattr(sender, 'first_name', None),
            'sender_last_name': getattr(sender, 'last_name', None),
            'text': text,
            'timestamp': int(message.date.timestamp()),
        }

        db.insert_message(msg_data)
        db.update_sync_state(chat_id, message.id)

        sender_name = getattr(sender, 'username', None) or getattr(sender, 'first_name', 'Unknown')
        timestamp = datetime.fromtimestamp(int(message.date.timestamp())).strftime('%H:%M:%S')
        print(f"[{timestamp}] {sender_name}: {text[:100]}")

    print("[telecrawl tail] Running... Press Ctrl+C to stop.")
    await client.run_until_disconnected()
