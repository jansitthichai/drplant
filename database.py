import sqlite3
import os
from datetime import datetime

# On Vercel the filesystem is ephemeral; use /tmp so writes succeed.
if os.getenv('VERCEL'):
    DB_FILE = '/tmp/drplant.db'
else:
    DB_FILE = os.getenv('DB_FILE', 'drplant.db')

CHAT_HISTORY_LIMIT = 8


def get_db_connection():
    parent = os.path.dirname(DB_FILE)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes the SQLite database."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                message_id TEXT,
                analysis_result TEXT,
                status TEXT,
                user_feedback TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_history_user_time
            ON chat_history (user_id, timestamp DESC)
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database Initialization Error: {e}")
        raise


def log_feedback(user_id, message_id, analysis_result, status='pending'):
    """Logs user feedback or initial prediction."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO feedback (user_id, message_id, analysis_result, status, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, message_id, analysis_result, status, datetime.now()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error logging feedback: {e}")
        return False


def update_feedback(user_id, user_feedback):
    """Updates the latest pending feedback for a user."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            UPDATE feedback
            SET user_feedback = ?, status = 'corrected'
            WHERE id = (
                SELECT id FROM feedback
                WHERE user_id = ? AND status = 'pending'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
            )
        """, (user_feedback, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating feedback: {e}")
        return False


def save_chat(user_id, role, content):
    """Saves one chat turn for a user. role should be 'user' or 'assistant'."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO chat_history (user_id, role, content)
            VALUES (?, ?, ?)
        """, (user_id, role, content))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Database Error (save_chat): {e}")
        return False


def get_recent_chat(user_id, limit=CHAT_HISTORY_LIMIT):
    """
    Returns recent chat turns for a user as a list of (role, content),
    oldest first (suitable for prompt context).
    """
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT role, content FROM (
                SELECT role, content, timestamp, id
                FROM chat_history
                WHERE user_id = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            ) AS recent
            ORDER BY timestamp ASC, id ASC
        """, (user_id, limit))
        rows = [(row["role"], row["content"]) for row in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"Database Error (get_recent_chat): {e}")
        return []


def get_latest_prediction(user_id):
    """Returns the most recent image analysis text for this user, or None."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT analysis_result FROM feedback
            WHERE user_id = ? AND analysis_result IS NOT NULL AND analysis_result != ''
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """, (user_id,))
        row = c.fetchone()
        conn.close()
        return row["analysis_result"] if row else None
    except Exception as e:
        print(f"Database Error (get_latest_prediction): {e}")
        return None


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
