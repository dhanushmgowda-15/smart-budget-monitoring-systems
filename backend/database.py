"""Database setup and SQLite connection management for SpendSense.

Uses Python's built-in sqlite3 module with parameterized queries
to ensure thread safety and prevent SQL injection.
"""

import os
import sqlite3
from typing import Generator
from contextlib import contextmanager

def get_db_path() -> str:
    """Returns the current database path from environment or default."""
    default = "/tmp/spendsense.db" if os.environ.get("VERCEL") else "spendsense.db"
    return os.environ.get("SPENDSENSE_DB_PATH", default)


def _create_schema(conn: sqlite3.Connection) -> None:
    """Creates the tables and indexes if they do not already exist."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            note TEXT DEFAULT ''
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            UNIQUE(month, category)
        );
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_budgets_month ON budgets(month);")
    conn.commit()


def get_db_connection(db_path: str = None) -> sqlite3.Connection:
    """Creates and returns a connection to the SQLite database.
    
    Sets row_factory to sqlite3.Row for dictionary-like column access.
    Automatically initializes schema if the database file is new.
    """
    target = db_path or get_db_path()
    is_new = not os.path.exists(target) or os.path.getsize(target) == 0
    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency between readers and writers
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    if is_new:
        _create_schema(conn)
    return conn


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency yielding a database connection with auto-commit and cleanup."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str = None) -> None:
    """Initializes the database schema if tables do not already exist."""
    target_path = db_path or get_db_path()
    conn = sqlite3.connect(target_path)
    try:
        _create_schema(conn)
    finally:
        conn.close()
