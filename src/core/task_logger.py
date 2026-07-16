import sqlite3
import os
import json
import logging
from typing import Dict, Any

logger = logging.getLogger("MultiAgent.TaskLogger")

DB_PATH = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "tasks.db"))

def _get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            event_type TEXT,
            task_id TEXT,
            details TEXT
        )
    ''')
    conn.commit()
    return conn

def log_task_event(event: Dict[str, Any]):
    try:
        conn = _get_connection()
        conn.execute(
            "INSERT INTO task_events (timestamp, event_type, task_id, details) VALUES (?, ?, ?, ?)",
            (
                event.get("timestamp", ""),
                event.get("type", ""),
                event.get("task_id", ""),
                json.dumps(event.get("details", {}), default=str)
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to log task event to SQLite: {e}")
