import sqlite3
from pathlib import Path

# Resolve to the project root regardless of the current working directory:
# backend/app/db/session.py -> db -> app -> backend -> <project root>
DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "vulnerable_app.db"


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email    TEXT,
            password TEXT
        )
        """
    )
    conn.commit()
    conn.close()
