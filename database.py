import sqlite3
import os
from datetime import datetime

DB_FILE = 'drplant.db'

def get_db_connection():
    os.makedirs(os.path.dirname(DB_FILE) or '.', exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            message_id TEXT,
            analysis_result TEXT,
            status TEXT,
            user_feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def log_feedback(user_id, message_id, analysis_result, status='pending'):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO feedback (user_id, message_id, analysis_result, status, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, message_id, analysis_result, status, datetime.now()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging feedback: {e}")

def update_feedback(user_id, user_feedback):
    # This is a simple implementation that updates the most recent pending feedback for the user
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            UPDATE feedback
            SET user_feedback = ?, status = 'corrected'
            WHERE user_id = ? AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1
        ''', (user_feedback, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating feedback: {e}")
