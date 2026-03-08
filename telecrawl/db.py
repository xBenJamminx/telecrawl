"""
Database management for telegaf
Handles SQLite schema, FTS5 setup, and CRUD operations
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime


class TeleCrawlDB:
    def __init__(self, db_path: str = "telecrawl.db"):
        self.db_path = Path(db_path).expanduser()
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        """Initialize database connection and create schema if needed"""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        """Create tables and FTS5 virtual table"""
        cursor = self.conn.cursor()

        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                topic_id INTEGER,
                sender_id INTEGER,
                sender_username TEXT,
                sender_first_name TEXT,
                sender_last_name TEXT,
                text TEXT,
                timestamp INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)

        # FTS5 virtual table for full-text search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                text,
                sender_username,
                sender_first_name,
                sender_last_name,
                content=messages,
                content_rowid=message_id,
                tokenize='porter unicode61'
            )
        """)

        # Triggers to keep FTS5 in sync
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, text, sender_username, sender_first_name, sender_last_name)
                VALUES (new.message_id, new.text, new.sender_username, new.sender_first_name, new.sender_last_name);
            END
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                DELETE FROM messages_fts WHERE rowid = old.message_id;
            END
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                DELETE FROM messages_fts WHERE rowid = old.message_id;
                INSERT INTO messages_fts(rowid, text, sender_username, sender_first_name, sender_last_name)
                VALUES (new.message_id, new.text, new.sender_username, new.sender_first_name, new.sender_last_name);
            END
        """)

        # Sync state table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_state (
                chat_id INTEGER PRIMARY KEY,
                last_message_id INTEGER NOT NULL,
                last_sync_at INTEGER NOT NULL
            )
        """)

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_topic ON messages(topic_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)")

        self.conn.commit()

    def insert_message(self, message: Dict[str, Any]) -> bool:
        """Insert a message into the database"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO messages
                (message_id, chat_id, topic_id, sender_id, sender_username,
                 sender_first_name, sender_last_name, text, timestamp, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message['message_id'],
                message['chat_id'],
                message.get('topic_id'),
                message.get('sender_id'),
                message.get('sender_username'),
                message.get('sender_first_name'),
                message.get('sender_last_name'),
                message.get('text'),
                message['timestamp'],
                int(datetime.now().timestamp())
            ))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error inserting message: {e}")
            return False

    def get_last_message_id(self, chat_id: int) -> Optional[int]:
        """Get the last synced message ID for a chat"""
        cursor = self.conn.cursor()
        result = cursor.execute(
            "SELECT last_message_id FROM sync_state WHERE chat_id = ?",
            (chat_id,)
        ).fetchone()
        return result['last_message_id'] if result else None

    def update_sync_state(self, chat_id: int, last_message_id: int):
        """Update sync state for a chat"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO sync_state (chat_id, last_message_id, last_sync_at)
            VALUES (?, ?, ?)
        """, (chat_id, last_message_id, int(datetime.now().timestamp())))
        self.conn.commit()

    def search(self, query: str, chat_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Search messages using FTS5 with BM25 ranking"""
        cursor = self.conn.cursor()

        if chat_id:
            sql = """
                SELECT m.*, bm25(messages_fts) as rank
                FROM messages m
                JOIN messages_fts ON m.message_id = messages_fts.rowid
                WHERE messages_fts MATCH ? AND m.chat_id = ?
                ORDER BY rank
                LIMIT ?
            """
            results = cursor.execute(sql, (query, chat_id, limit)).fetchall()
        else:
            sql = """
                SELECT m.*, bm25(messages_fts) as rank
                FROM messages m
                JOIN messages_fts ON m.message_id = messages_fts.rowid
                WHERE messages_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            results = cursor.execute(sql, (query, limit)).fetchall()

        return [{k: row[k] for k in row.keys()} for row in results]

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        cursor = self.conn.cursor()

        total_messages = cursor.execute("SELECT COUNT(*) as count FROM messages").fetchone()[0]
        total_chats = cursor.execute("SELECT COUNT(DISTINCT chat_id) as count FROM messages").fetchone()[0]

        chat_stats = cursor.execute("""
            SELECT chat_id, COUNT(*) as message_count
            FROM messages
            GROUP BY chat_id
            ORDER BY message_count DESC
        """).fetchall()

        return {
            'total_messages': total_messages,
            'total_chats': total_chats,
            'chats': [dict(row) for row in chat_stats]
        }

    def verify_integrity(self) -> Dict[str, Any]:
        """Verify database integrity"""
        cursor = self.conn.cursor()

        # Check FTS5 sync
        fts_count = cursor.execute("SELECT COUNT(*) as count FROM messages_fts").fetchone()[0]
        msg_count = cursor.execute("SELECT COUNT(*) as count FROM messages").fetchone()[0]

        # Check for orphaned FTS entries
        orphaned = cursor.execute("""
            SELECT COUNT(*) as count
            FROM messages_fts
            WHERE rowid NOT IN (SELECT message_id FROM messages)
        """).fetchone()[0]

        # Check for messages without FTS
        missing_fts = cursor.execute("""
            SELECT COUNT(*) as count
            FROM messages
            WHERE message_id NOT IN (SELECT rowid FROM messages_fts)
        """).fetchone()[0]

        return {
            'messages_count': msg_count,
            'fts_count': fts_count,
            'orphaned_fts': orphaned,
            'missing_fts': missing_fts,
            'healthy': (msg_count == fts_count and orphaned == 0 and missing_fts == 0)
        }

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
