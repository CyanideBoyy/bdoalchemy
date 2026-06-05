"""
Database initialization for the standalone Alchemy app.
"""

import sqlite3
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
DATABASE_NAME = os.path.join(PROJECT_ROOT, "bdoalchemy.db")


def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_alchemy_db():
    """Initialize alchemy stock tables (elixirs, materials, draughts)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alchemy_elixir_stock (
                elixir_key TEXT PRIMARY KEY,
                quantity   INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alchemy_material_stock (
                material_key TEXT PRIMARY KEY,
                quantity     INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alchemy_draught_stock (
                draught_key TEXT PRIMARY KEY,
                quantity    INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        raise Exception(f"Error initializing alchemy database: {str(e)}")
