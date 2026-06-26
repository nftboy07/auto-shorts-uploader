import os
import yt_dlp
import json
import asyncio
import re
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

from utils import app_logger, error_logger
from database import get_active_accounts, update_account_checked, video_exists, add_video, file_hash_exists
from utils import calculate_file_hash, get_video_metadata, trim_video
from config import load_settings

BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)


def _get_ydl_opts(username: str, limit: int, proxy: Optional[str] = None) -> dict:
    """Build yt-dlp options for Instagram profile reels scraping."""
    settings = load_settings()
    cookies_path = None

    # Look for cookies file
    possible_cookies = [
        str(BASE_DIR / "config" / "instagram_cookies.txt"),
        str(BASE_DIR / "instagram_cookies.txt"),
        "/tmp/instagram_cookies.txt",
    ]
    for cp in possible_cookies:
        if os.path.exists(cp):
            cookies_path = cp
            break

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "playlistend": limit,
        "outtmpl": str(DOWNLOADS_DIR / "%(uploader_id)s_%(id)s.%(ext)s"),
        "format": "mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "retries": 3,
        "fragment_retries": 3,
        "extractor_args": {
            "instagram": {
                "player_client": ["android"],
            }
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 12; Pixel 5) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Mobile Safari/537.36 Instagram/279.0.0.21.120"
            ),
        },
    }

    if cookies_path:
        opts["cookiefile"] = cookies_path
        app_logger.info(f"Using Instagram cookies from: {cookies_path}")

    if proxy:
        opts["proxy"] = proxy
        app_logger.info(f"Using proxy for yt-dlp: {proxy}")

    return opts


def _process_downloaded_entry(info: Dict[str, Any]) -> Optional[str]:
    """
    Validates and saves a downloaded reel entry to the database.
    Returns local_path if successful, None if rejected/failed.
    """
    video_id = info.get("id", "")
    if not video_id:
        return None

    if video_exists(video_id):
        app_logger.info(f"Reel {video_id} already in database, skipping.")
        return None

    # Locate the downloaded file
    ext = info.get("ext", "mp4")
    uploader_id = info.get("uploader_id", "unknown")
    local_path = str(DOWNLOADS_DIR / f"{uploader_id}_{video_id}.{ext}")

    # Fallback scan
    if not os.path.exists(local_path):
        candidates = list(DOWNLOADS_DIR.glob(f"*{video_id}*"))
        candidates = [c for c in candidates if c.suffix in (".mp4", ".mkv", ".webm")]
        if candidates:
            local_path = str(candidates[0])
        else:
            app_logger.error(f"Downloaded file not found for reel {video_id}")
            return None

    # Inspect metadata via ffprobe
    metadata = get_video_metadata(local_path)
    if not metadata:
        app_logger.warning(f"Failed to get metadata for {video_id}. Rejecting.")
        try:
            os.remove(local_path)
        except Exception:
            pass
        return None

    duration = metadata["duration"]

    # Trim if over 60s (YouTube Shorts limit)
    if duration > 60.0:
        app_logger.info(f"Video {video_id} is {duration:.1f}s, trimming to 60s...")
        trimmed_path = str(DOWNLOADS_DIR / f"{video_id}_trimmed.mp4")
        if trim_video(local_path, trimmed_path, 60.0):
            try:
                os.remove(local_path)
            except Exception:
                pass
            local_path = trimmed_path
            metadata = get_video_metadata(local_path)
            if not metadata:
                return None
            duration = metadata["duration"]
        else:
            app_logger.warning(f"Failed to trim {video_id}. Rejecting.")
            try:
                os.remove(local_path)
            except Exception:
                pass
            return None

    # Duplicate hash check
    file_hash = calculate_file_hash(local_path)
    if file_hash_exists(file_hash):
        app_logger.warning(f"Reel {video_id} duplicate hash detected. Rejecting.")
        try:
            os.remove(local_path)
        except Exception:
            pass
        return None

    # Extract caption / creator
    caption = info.get("description") or info.get("title") or f"Reel by @{uploader_id}"
    creator = info.get("uploader") or uploader_id or "unknown"

    # Save to DB
    success = add_video(
        video_id=video_id,
        creator=creator,
        caption=caption,
        duration=duration,
        file_hash=file_hash,
        local_path=local_path,
    )

    if success:
        app_logger.info(f"Saved reel {video_id} (by @{creator}) to queue.")
        return local_path
    else:
        app_logger.error(f"DB insert failed for {video_id}.")
        return None


def download_profile_reels(username: str, limit: int = 24, proxy: Optional[str] = None) -> List[str]:
    """
    Downloads the latest `limit` reels from an Instagram profile using yt-dlp.
    Returns list of local file paths successfully saved to the queue DB.
    """
    profile_url = f"https://www.instagram.com/{username}/reels/"
    app_logger.info(f"Starting yt-dlp download for @{username} (limit={limit}): {profile_url}")

    opts = _get_ydl_opts(username, limit, proxy)
    downloaded_paths = []

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(profile_url, download=True)

            if not result:
                app_logger.error(f"yt-dlp returned no result for @{username}")
                return []

            entries = result.get("entries", [result])
            app_logger.info(f"yt-dlp fetched {len(entries)} entries for @{username}")

            for entry in entries:
                if not entry:
                    continue
                try:
                    path = _process_downloaded_entry(entry)
                    if path:
                        downloaded_paths.append(path)
                except Exception as e:
                    error_logger.error(f"Error processing entry for @{username}: {e}")
                    continue

    except yt_dlp.utils.DownloadError as e:
        error_logger.error(f"yt-dlp DownloadError for @{username}: {e}")
    except Exception as e:
        error_logger.error(f"Unexpected error downloading @{username}: {e}")

    app_logger.info(f"Finished download for @{username}: {len(downloaded_paths)} reels added to queue.")
    return downloaded_paths


class InstagramWatcher:
    """
    Monitors Instagram accounts for new reels using yt-dlp (not instaloader).
    instaloader's GraphQL get_posts() was blocked with 400 errors; yt-dlp is more resilient.
    """

    def __init__(self):
        # No instaloader needed anymore
        pass

    def authenticate(self) -> bool:
        """No-op: yt-dlp handles auth via cookies or anonymous access."""
        return True

    def check_new_reels(self, max_posts_per_profile: int = 24, proxy: Optional[str] = None) -> List[str]:
        """
        Scans all active accounts from database for new Reels using yt-dlp.
        Downloads valid reels and returns a list of downloaded local paths.
        """
        accounts = get_active_accounts()
        if not accounts:
            app_logger.info("No active Instagram accounts to watch.")
            return []

        all_downloaded = []

        for account in accounts:
            app_logger.info(f"Scanning Instagram account via yt-dlp: @{account}")
            try:
                paths = download_profile_reels(account, limit=max_posts_per_profile, proxy=proxy)
                all_downloaded.extend(paths)
                update_account_checked(account)
            except Exception as e:
                error_logger.error(f"Error scanning @{account}: {e}")

        return all_downloaded
