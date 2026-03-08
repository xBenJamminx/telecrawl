"""
Telegram message syncing via Bot API
Handles incremental sync from Telegram groups to local SQLite
"""

import os
import time
from typing import Optional, List, Dict, Any
import requests
from .db import TelegrafDB


class TelegramSyncer:
    def __init__(self, bot_token: str, db: TelegrafDB):
        self.bot_token = bot_token
        self.db = db
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def _make_request(self, method: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make a request to Telegram Bot API"""
        url = f"{self.base_url}/{method}"
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"API request failed: {e}")
            return {'ok': False, 'error': str(e)}

    def get_updates(self, offset: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get updates from Telegram"""
        params = {'limit': limit, 'timeout': 30}
        if offset:
            params['offset'] = offset

        result = self._make_request('getUpdates', params)

        if result.get('ok'):
            return result.get('result', [])
        return []

    def sync_chat(self, chat_id: int, verbose: bool = False) -> int:
        """
        Sync messages from a specific chat
        Returns number of new messages synced
        """
        last_message_id = self.db.get_last_message_id(chat_id)
        new_messages = 0
        offset = None

        if verbose:
            print(f"Syncing chat {chat_id} (last message: {last_message_id or 'none'})")

        while True:
            updates = self.get_updates(offset=offset)

            if not updates:
                break

            for update in updates:
                # Update offset for next call
                offset = update['update_id'] + 1

                # Extract message
                message = update.get('message') or update.get('channel_post')
                if not message:
                    continue

                # Check if it's from our target chat
                msg_chat_id = message.get('chat', {}).get('id')
                if msg_chat_id != chat_id:
                    continue

                msg_id = message.get('message_id')

                # Skip if we've already synced this message
                if last_message_id and msg_id <= last_message_id:
                    continue

                # Extract message data
                msg_data = self._parse_message(message)

                if msg_data:
                    if self.db.insert_message(msg_data):
                        new_messages += 1
                        if verbose:
                            sender = msg_data.get('sender_username') or msg_data.get('sender_first_name') or 'Unknown'
                            print(f"  [{msg_id}] {sender}: {msg_data.get('text', '')[:50]}")

                        # Update sync state with highest message ID
                        if not last_message_id or msg_id > last_message_id:
                            last_message_id = msg_id

            # If we got fewer updates than limit, we've reached the end
            if len(updates) < 100:
                break

        # Update sync state
        if last_message_id:
            self.db.update_sync_state(chat_id, last_message_id)

        return new_messages

    def _parse_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse Telegram message into our schema"""
        msg_id = message.get('message_id')
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text') or message.get('caption')

        # Skip messages without text
        if not text:
            return None

        sender = message.get('from') or {}

        return {
            'message_id': msg_id,
            'chat_id': chat_id,
            'topic_id': message.get('message_thread_id'),  # For forum/topic groups
            'sender_id': sender.get('id'),
            'sender_username': sender.get('username'),
            'sender_first_name': sender.get('first_name'),
            'sender_last_name': sender.get('last_name'),
            'text': text,
            'timestamp': message.get('date', int(time.time()))
        }

    def sync_multiple_chats(self, chat_ids: List[int], verbose: bool = False) -> Dict[int, int]:
        """
        Sync multiple chats
        Returns dict of chat_id -> new_messages_count
        """
        results = {}
        for chat_id in chat_ids:
            try:
                count = self.sync_chat(chat_id, verbose=verbose)
                results[chat_id] = count
                if verbose:
                    print(f"Chat {chat_id}: synced {count} new messages")
            except Exception as e:
                print(f"Error syncing chat {chat_id}: {e}")
                results[chat_id] = 0

        return results
