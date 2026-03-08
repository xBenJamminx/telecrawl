"""
Search interface for telegaf
Provides high-level search and query functions
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from .db import TelegrafDB


class TeleCrawlQuery:
    def __init__(self, db: TelegrafDB):
        self.db = db

    def search(self,
               query: str,
               chat_id: Optional[int] = None,
               limit: int = 50,
               format_output: bool = True) -> List[Dict[str, Any]]:
        """
        Search messages with optional formatting
        """
        results = self.db.search(query, chat_id=chat_id, limit=limit)

        if format_output:
            return [self._format_result(r) for r in results]
        return results

    def _format_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Format search result for display"""
        sender = result.get('sender_username') or result.get('sender_first_name') or 'Unknown'
        if result.get('sender_last_name'):
            sender = f"{result['sender_first_name']} {result['sender_last_name']}"

        timestamp = datetime.fromtimestamp(result['timestamp']).strftime('%Y-%m-%d %H:%M:%S')

        return {
            'message_id': result['message_id'],
            'chat_id': result['chat_id'],
            'topic_id': result.get('topic_id'),
            'sender': sender,
            'text': result.get('text', ''),
            'timestamp': timestamp,
            'relevance': abs(result.get('rank', 0))  # BM25 score (negative, so abs it)
        }

    def get_recent(self, chat_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent messages"""
        cursor = self.db.conn.cursor()

        if chat_id:
            results = cursor.execute("""
                SELECT * FROM messages
                WHERE chat_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (chat_id, limit)).fetchall()
        else:
            results = cursor.execute("""
                SELECT * FROM messages
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()

        return [self._format_result(dict(r)) for r in results]

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        return self.db.get_stats()

    def verify(self) -> Dict[str, Any]:
        """Verify database integrity"""
        return self.db.verify_integrity()
