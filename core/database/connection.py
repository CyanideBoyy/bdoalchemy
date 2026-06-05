"""
Database Connection Management Module

This module handles all database connection logic, providing:
- Safe connection creation with timeout and retry handling
- Context manager for automatic commit/rollback
- Thread-safe connection handling
- Centralized database path configuration
"""

import sqlite3
import os
import time
from contextlib import contextmanager
from typing import Generator

# Get the directory where this script is located and go up to project root
# core/database/connection.py -> go up 2 levels to project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
DATABASE_PATH = os.path.join(PROJECT_ROOT, "bdoalchemy.db")


def get_db_path() -> str:
    """
    Get the database file path.

    Returns:
        str: Absolute path to the database file
    """
    return DATABASE_PATH


@contextmanager
def get_connection(
    db_path: str = None, timeout: float = 30.0, retries: int = 5
) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for safe database connections with automatic cleanup.

    Args:
        db_path: Path to database file (defaults to PROJECT database)
        timeout: Maximum time to wait for database lock (seconds)
        retries: Number of retry attempts if database is locked

    Yields:
        sqlite3.Connection: Database connection object

    Raises:
        sqlite3.OperationalError: If connection fails after all retries
    """
    if db_path is None:
        db_path = DATABASE_PATH

    conn = None
    base_delay = 0.1

    for attempt in range(retries):
        try:
            conn = sqlite3.connect(
                db_path,
                timeout=timeout,
                check_same_thread=False,
            )

            conn.row_factory = sqlite3.Row

            conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)};")
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA cache_size=10000;")
            conn.execute("PRAGMA temp_store=MEMORY;")
            conn.execute("PRAGMA mmap_size=268435456;")
            conn.execute("PRAGMA foreign_keys=ON;")

            conn.execute("SELECT 1;").fetchone()

            break

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if (
                "database is locked" in error_msg or "busy" in error_msg
            ) and attempt < retries - 1:
                delay = base_delay * (2**attempt)
                print(
                    f"Database busy on attempt {attempt + 1}/{retries}, waiting {delay:.2f}s..."
                )
                time.sleep(delay)
                continue
            else:
                print(f"Database error after {attempt + 1} attempts: {str(e)}")
                print(f"Database location: {db_path}")
                raise

        except Exception as e:
            print(f"Unexpected database error: {str(e)}")
            raise

    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Transaction rolled back due to error: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()
