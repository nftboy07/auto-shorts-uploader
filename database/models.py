import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional
from .db import db_session, log_action

# --- Accounts ---
def add_account(username: str) -> bool:
    """Adds a new Instagram account to monitor."""
    username = username.strip().lower()
    try:
        with db_session() as conn:
            conn.execute(
                "INSERT INTO accounts (username) VALUES (?) ON CONFLICT(username) DO UPDATE SET is_active=1",
                (username,)
            )
        log_action("add_account", f"Added account: {username}")
        return True
    except Exception as e:
        log_action("error", f"Failed to add account {username}: {e}")
        return False

def remove_account(username: str) -> bool:
    """Disables or removes an Instagram account from monitoring."""
    username = username.strip().lower()
    try:
        with db_session() as conn:
            conn.execute("DELETE FROM accounts WHERE username = ?", (username,))
        log_action("remove_account", f"Removed account: {username}")
        return True
    except Exception as e:
        log_action("error", f"Failed to remove account {username}: {e}")
        return False

def list_accounts() -> List[Dict[str, Any]]:
    """Lists all monitored accounts."""
    with db_session() as conn:
        rows = conn.execute("SELECT username, is_active, last_checked, added_date FROM accounts").fetchall()
        return [dict(r) for r in rows]

def get_active_accounts() -> List[str]:
    """Returns usernames of active accounts."""
    with db_session() as conn:
        rows = conn.execute("SELECT username FROM accounts WHERE is_active = 1").fetchall()
        return [r["username"] for r in rows]

def update_account_checked(username: str) -> None:
    """Updates the last_checked timestamp for an account."""
    username = username.strip().lower()
    now_str = datetime.now().isoformat()
    with db_session() as conn:
        conn.execute(
            "UPDATE accounts SET last_checked = ? WHERE username = ?",
            (now_str, username)
        )

# --- Videos ---
def add_video(video_id: str, creator: str, caption: str, duration: float, file_hash: str, local_path: str) -> bool:
    """Saves metadata for a downloaded video."""
    creator = creator.strip().lower()
    try:
        with db_session() as conn:
            conn.execute(
                """INSERT INTO videos (video_id, creator, caption, duration, file_hash, local_path, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'downloaded')""",
                (video_id, creator, caption, duration, file_hash, local_path)
            )
        log_action("add_video", f"Saved video {video_id} by {creator}")
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        log_action("error", f"Failed to add video {video_id}: {e}")
        return False

def video_exists(video_id: str) -> bool:
    """Checks if a video_id is already processed."""
    with db_session() as conn:
        row = conn.execute("SELECT 1 FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        return row is not None

def file_hash_exists(file_hash: str) -> bool:
    """Checks if a file hash is already processed (prevents duplicates)."""
    with db_session() as conn:
        row = conn.execute("SELECT 1 FROM videos WHERE file_hash = ?", (file_hash,)).fetchone()
        return row is not None

def update_video_status(video_id: str, status: str) -> None:
    """Updates the status of a video."""
    with db_session() as conn:
        conn.execute("UPDATE videos SET status = ? WHERE video_id = ?", (status, video_id))

# --- Uploads ---
def add_upload(youtube_id: str, video_id: str, status: str = "uploaded") -> bool:
    """Records a successful or scheduled upload."""
    try:
        with db_session() as conn:
            conn.execute(
                "INSERT INTO uploads (youtube_id, video_id, status) VALUES (?, ?, ?)",
                (youtube_id, video_id, status)
            )
            conn.execute(
                "UPDATE videos SET status = 'uploaded' WHERE video_id = ?",
                (video_id,)
            )
        log_action("add_upload", f"Video {video_id} uploaded to YouTube as {youtube_id}")
        return True
    except Exception as e:
        log_action("error", f"Failed to add upload record for {video_id}: {e}")
        return False

def get_last_upload() -> Optional[Dict[str, Any]]:
    """Retrieves metadata of the last uploaded video."""
    with db_session() as conn:
        row = conn.execute(
            """SELECT u.youtube_id, u.upload_time, u.status, v.video_id, v.creator, v.caption
               FROM uploads u
               JOIN videos v ON u.video_id = v.video_id
               ORDER BY u.upload_time DESC LIMIT 1"""
        ).fetchone()
        return dict(row) if row else None

def get_upload_queue() -> List[Dict[str, Any]]:
    """Retrieves videos that have been downloaded but not yet uploaded."""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT video_id, creator, caption, duration, local_path, download_date FROM videos WHERE status = 'downloaded'"
        ).fetchall()
        return [dict(r) for r in rows]

# --- Failed Uploads ---
def record_upload_failure(video_id: str, error: str) -> None:
    """Records a failure to upload a video, incrementing attempts."""
    now_str = datetime.now().isoformat()
    with db_session() as conn:
        conn.execute(
            """INSERT INTO failed_uploads (video_id, attempts, last_error, last_attempt)
               VALUES (?, 1, ?, ?)
               ON CONFLICT(video_id) DO UPDATE SET
               attempts = attempts + 1,
               last_error = ?,
               last_attempt = ?""",
            (video_id, error, now_str, error, now_str)
        )
        conn.execute("UPDATE videos SET status = 'failed' WHERE video_id = ?", (video_id,))
    log_action("upload_failure", f"Upload failed for {video_id}: {error}")

def get_failed_uploads() -> List[Dict[str, Any]]:
    """Gets list of failed uploads."""
    with db_session() as conn:
        rows = conn.execute(
            """SELECT f.video_id, f.attempts, f.last_error, f.last_attempt, v.creator, v.local_path
               FROM failed_uploads f
               JOIN videos v ON f.video_id = v.video_id"""
        ).fetchall()
        return [dict(r) for r in rows]

# --- Proxies ---
def add_proxy(proxy_url: str) -> bool:
    """Registers a proxy."""
    try:
        with db_session() as conn:
            conn.execute(
                "INSERT INTO proxies (proxy_url) VALUES (?) ON CONFLICT(proxy_url) DO UPDATE SET status='active', failure_count=0",
                (proxy_url,)
            )
        log_action("add_proxy", f"Added proxy: {proxy_url}")
        return True
    except Exception as e:
        return False

def remove_proxy(proxy_url: str) -> bool:
    """Removes a proxy."""
    try:
        with db_session() as conn:
            conn.execute("DELETE FROM proxies WHERE proxy_url = ?", (proxy_url,))
        log_action("remove_proxy", f"Removed proxy: {proxy_url}")
        return True
    except Exception as e:
        return False

def get_all_proxies() -> List[Dict[str, Any]]:
    """Gets list of all proxies."""
    with db_session() as conn:
        rows = conn.execute("SELECT proxy_url, status, last_used, failure_count FROM proxies").fetchall()
        return [dict(r) for r in rows]

def get_active_proxies() -> List[str]:
    """Gets all active proxies."""
    with db_session() as conn:
        rows = conn.execute("SELECT proxy_url FROM proxies WHERE status = 'active'").fetchall()
        return [r["proxy_url"] for r in rows]

def update_proxy_status(proxy_url: str, status: str) -> None:
    """Updates proxy status."""
    with db_session() as conn:
        conn.execute("UPDATE proxies SET status = ? WHERE proxy_url = ?", (status, proxy_url))

def record_proxy_failure(proxy_url: str, error: str) -> None:
    """Updates proxy failure details."""
    now_str = datetime.now().isoformat()
    with db_session() as conn:
        conn.execute(
            """UPDATE proxies SET
               failure_count = failure_count + 1,
               last_used = ?
               WHERE proxy_url = ?""",
            (now_str, proxy_url)
        )
        # Mark inactive after 5 straight failures
        conn.execute(
            "UPDATE proxies SET status = 'inactive' WHERE proxy_url = ? AND failure_count >= 5",
            (proxy_url,)
        )

# --- Analytics ---
def update_analytics(date_str: str, views: int = 0, likes: int = 0, subs: int = 0, uploaded: int = 0) -> None:
    """Aggregates daily statistics."""
    with db_session() as conn:
        conn.execute(
            """INSERT INTO analytics (date, views, likes, subs_gained, videos_uploaded)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
               views = views + ?,
               likes = likes + ?,
               subs_gained = subs_gained + ?,
               videos_uploaded = videos_uploaded + ?""",
            (date_str, views, likes, subs, uploaded, views, likes, subs, uploaded)
        )

def get_analytics_summary() -> List[Dict[str, Any]]:
    """Gets daily analytics reports."""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT date, views, likes, subs_gained, videos_uploaded FROM analytics ORDER BY date DESC LIMIT 30"
        ).fetchall()
        return [dict(r) for r in rows]

def get_system_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Gets general action logs."""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT id, timestamp, action, details FROM history ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
