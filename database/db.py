import sqlite3
import os
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

BASE_DIR = Path(__file__).resolve().parent.parent
DB_FILE = BASE_DIR / "database" / "shortsbot.db"

def get_connection() -> sqlite3.Connection:
    """Returns a connection to the SQLite database."""
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def db_session():
    """Context manager to ensure database connections are closed and committed."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db() -> None:
    """Initializes the database schema if it doesn't exist."""
    with db_session() as conn:
        cursor = conn.cursor()
        
        # Accounts to monitor
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                username TEXT PRIMARY KEY,
                is_active INTEGER DEFAULT 1,
                last_checked TEXT,
                added_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Videos metadata
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                creator TEXT NOT NULL,
                caption TEXT,
                duration REAL,
                file_hash TEXT UNIQUE,
                download_date TEXT DEFAULT CURRENT_TIMESTAMP,
                local_path TEXT,
                status TEXT DEFAULT 'downloaded'
            )
        """)
        
        # Upload status and metrics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                youtube_id TEXT PRIMARY KEY,
                video_id TEXT,
                upload_time TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT,
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                retention REAL DEFAULT 0.0,
                subs_gained INTEGER DEFAULT 0,
                FOREIGN KEY (video_id) REFERENCES videos(video_id)
            )
        """)
        
        # Failed uploads and retry tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS failed_uploads (
                video_id TEXT PRIMARY KEY,
                attempts INTEGER DEFAULT 0,
                last_error TEXT,
                last_attempt TEXT,
                FOREIGN KEY (video_id) REFERENCES videos(video_id)
            )
        """)
        
        # Proxy configurations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS proxies (
                proxy_url TEXT PRIMARY KEY,
                status TEXT DEFAULT 'active',
                last_used TEXT,
                failure_count INTEGER DEFAULT 0
            )
        """)
        
        # Log records (for sqlite-based logging backup)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS db_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                level TEXT,
                message TEXT
            )
        """)
        
        # Daily aggregated analytics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analytics (
                date TEXT PRIMARY KEY,
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                subs_gained INTEGER DEFAULT 0,
                videos_uploaded INTEGER DEFAULT 0
            )
        """)
        
        # General action history log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                action TEXT,
                details TEXT
            )
        """)

def log_action(action: str, details: str) -> None:
    """Logs an action to the history table."""
    try:
        with db_session() as conn:
            conn.execute(
                "INSERT INTO history (action, details) VALUES (?, ?)", 
                (action, details)
            )
    except Exception as e:
        print(f"Failed to log action: {e}")
