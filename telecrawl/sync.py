"""
Telegram message syncing via Telethon (MTProto user API)
Provides full history access — unlike Bot API, which cannot read message history.
"""

import asyncio
import time
from typing import Optional, List, Dict, Any

from telethon import TelegramClient
from telethon.tl.types import Message

from .db import TeleCrawlDB


class TelegramSyncer:
    def __init__(self, client: TelegramClient, db: TeleCrawlDB):
        self.client = client
        self.db = db

    async def sync_chat(self, chat_id: int, full: bool = False, verbose: bool = False) -> int:
        """
        Sync messages from a Telegram chat using Telethon.

        Uses iter_messages with min_id for incremental sync.
        Full history access via MTProto — no Bot API limitations.

        Args:
            chat_id: Telegram chat/group ID
            full: If True, resync all messages from the beginning
            verbose: Print progress information

        Returns:
            Number of new messages synced
        """
        entity = await self.client.get_entity(chat_id)

        if full:
            min_id = 0
            if verbose:
                print(f"Full sync for chat {chat_id}")
        else:
            min_id = self.db.get_last_message_id(chat_id) or 0
            if verbose:
                print(f"Incremental sync for chat {chat_id} (after message {min_id})")

        new_messages = 0
        last_id = min_id
        batch = []

        async for message in self.client.iter_messages(
            entity,
            min_id=min_id,
            limit=None,
            reverse=True  # Oldest first for consistent ordering
        ):
            if not isinstance(message, Message):
                continue

            text = message.text or message.message
            if not text:
                # Skip media-only messages
                continue

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

            batch.append(msg_data)

            if len(batch) >= 100:
                for msg in batch:
                    self.db.insert_message(msg)
                    if msg['message_id'] > last_id:
                        last_id = msg['message_id']
                new_messages += len(batch)
                if verbose:
                    print(f"  Synced {new_messages} messages...")
                batch = []

        # Flush remaining
        for msg in batch:
            self.db.insert_message(msg)
            if msg['message_id'] > last_id:
                last_id = msg['message_id']
        new_messages += len(batch)

        # Update sync state
        if last_id > 0:
            self.db.update_sync_state(chat_id, last_id)

        if verbose:
            print(f"  Done. {new_messages} new messages synced.")

        return new_messages

    async def sync_multiple_chats(self, chat_ids: List[int], full: bool = False, verbose: bool = False) -> Dict[int, int]:
        """Sync multiple chats sequentially."""
        results = {}
        for chat_id in chat_ids:
            try:
                count = await self.sync_chat(chat_id, full=full, verbose=verbose)
                results[chat_id] = count
            except Exception as e:
                print(f"Error syncing chat {chat_id}: {e}")
                results[chat_id] = 0
        return results
