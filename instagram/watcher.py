import os
import yt_dlp
import subprocess
import json
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


def _find_cookies_path() -> Optional[str]:
    """Return first existing Instagram cookies file path."""
    candidates = [
        str(BASE_DIR / "config" / "instagram_cookies.txt"),
        str(BASE_DIR / "instagram_cookies.txt"),
        "/tmp/instagram_cookies.txt",
    ]
    for p in candidates:
        if os.path.exists(p):
            # Validate it has instagram content
            try:
                with open(p, "r") as f:
                    content = f.read()
                if "instagram.com" in content and "sessionid" in content:
                    app_logger.info(f"Valid Instagram cookies found at: {p}")
                    return p
                else:
                    app_logger.warning(f"Cookies file at {p} doesn't look valid (missing sessionid)")
            except Exception as e:
                app_logger.warning(f"Could not read cookies at {p}: {e}")
    app_logger.warning("No valid Instagram cookies file found - will try unauthenticated")
    return None


def _get_ydl_opts(limit: int, output_template: str, proxy: Optional[str] = None) -> dict:
    """Build yt-dlp options for Instagram downloading."""
    opts = {
        "quiet": False,          # Enable output so errors are visible in logs
        "no_warnings": False,    # Show warnings
        "extract_flat": "in_playlist",  # Get playlist entries without downloading first
        "playlistend": limit,
        "outtmpl": output_template,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/mp4/best",
        "merge_output_format": "mp4",
        "retries": 5,
        "fragment_retries": 5,
        "ignoreerrors": True,    # Skip individual failed videos, don't abort
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
            ),
        },
    }

    cookies_path = _find_cookies_path()
    if cookies_path:
        opts["cookiefile"] = cookies_path

    if proxy:
        opts["proxy"] = proxy
        app_logger.info(f"Using proxy for yt-dlp: {proxy}")

    return opts


def _save_entry_to_db(info: Dict[str, Any], downloaded_file: str) -> Optional[str]:
    """
    Validates a downloaded file and saves it to the database queue.
    Returns local_path on success, None on rejection.
    """
    video_id = info.get("id", "")
    uploader = info.get("uploader") or info.get("uploader_id") or info.get("channel") or "unknown"
    caption = info.get("description") or info.get("title") or f"Reel by @{uploader}"

    if not os.path.exists(downloaded_file):
        error_logger.error(f"File not found after download: {downloaded_file}")
        return None

    if video_exists(video_id):
        app_logger.info(f"Reel {video_id} already in DB, skipping.")
        try:
            os.remove(downloaded_file)
        except Exception:
            pass
        return None

    # ffprobe metadata
    metadata = get_video_metadata(downloaded_file)
    if not metadata:
        app_logger.warning(f"ffprobe failed for {video_id} at {downloaded_file}. Rejecting.")
        try:
            os.remove(downloaded_file)
        except Exception:
            pass
        return None

    duration = metadata["duration"]

    # Trim to 60s if needed
    if duration > 60.0:
        trimmed = str(DOWNLOADS_DIR / f"{video_id}_trimmed.mp4")
        app_logger.info(f"Trimming {video_id} from {duration:.1f}s to 60s...")
        if trim_video(downloaded_file, trimmed, 60.0):
            try:
                os.remove(downloaded_file)
            except Exception:
                pass
            downloaded_file = trimmed
            metadata = get_video_metadata(downloaded_file)
            if not metadata:
                return None
            duration = metadata["duration"]
        else:
            app_logger.warning(f"Trim failed for {video_id}. Rejecting.")
            try:
                os.remove(downloaded_file)
            except Exception:
                pass
            return None

    # Duplicate hash check
    file_hash = calculate_file_hash(downloaded_file)
    if file_hash_exists(file_hash):
        app_logger.warning(f"Duplicate content hash for {video_id}. Rejecting.")
        try:
            os.remove(downloaded_file)
        except Exception:
            pass
        return None

    # Save to DB
    success = add_video(
        video_id=video_id,
        creator=uploader,
        caption=caption[:500],
        duration=duration,
        file_hash=file_hash,
        local_path=downloaded_file,
    )

    if success:
        app_logger.info(f"Queued reel {video_id} by @{uploader} ({duration:.1f}s)")
        return downloaded_file
    else:
        error_logger.error(f"DB insert failed for {video_id}")
        return None


def download_profile_reels(username: str, limit: int = 24, proxy: Optional[str] = None) -> List[str]:
    """
    Downloads the latest `limit` reels from an Instagram profile using yt-dlp.
    Uses a two-step approach: first list URLs, then download each.
    Returns list of local file paths added to the DB queue.
    """
    profile_url = f"https://www.instagram.com/{username}/reels/"
    app_logger.info(f"Starting reel download for @{username} (limit={limit}) from {profile_url}")

    cookies_path = _find_cookies_path()
    downloaded_paths = []

    # ── Step 1: Extract reel URLs from the profile (flat list, no download) ──
    list_opts = {
        "quiet": False,
        "no_warnings": False,
        "extract_flat": True,
        "playlistend": limit,
        "ignoreerrors": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
            ),
        },
    }
    if cookies_path:
        list_opts["cookiefile"] = cookies_path
    if proxy:
        list_opts["proxy"] = proxy

    reel_urls = []
    try:
        with yt_dlp.YoutubeDL(list_opts) as ydl:
            app_logger.info(f"Extracting reel list for @{username}...")
            result = ydl.extract_info(profile_url, download=False)
            if result:
                entries = result.get("entries") or []
                for entry in entries:
                    if not entry:
                        continue
                    url = entry.get("url") or entry.get("webpage_url")
                    vid_id = entry.get("id")
                    if url:
                        reel_urls.append((vid_id, url))
                    elif vid_id:
                        reel_urls.append((vid_id, f"https://www.instagram.com/reel/{vid_id}/"))
                app_logger.info(f"Found {len(reel_urls)} reels for @{username}")
            else:
                error_logger.error(f"yt-dlp returned no result for @{username} profile page")
    except yt_dlp.utils.DownloadError as e:
        error_logger.error(f"yt-dlp DownloadError listing @{username}: {e}")
    except Exception as e:
        error_logger.error(f"Error listing reels for @{username}: {e}")

    if not reel_urls:
        # Fallback: try direct profile URL without /reels/
        app_logger.info(f"Trying fallback URL for @{username}: profile root")
        try:
            with yt_dlp.YoutubeDL(list_opts) as ydl:
                result = ydl.extract_info(f"https://www.instagram.com/{username}/", download=False)
                if result:
                    entries = result.get("entries") or []
                    for entry in entries:
                        if not entry:
                            continue
                        url = entry.get("url") or entry.get("webpage_url")
                        vid_id = entry.get("id")
                        if url:
                            reel_urls.append((vid_id, url))
                        elif vid_id:
                            reel_urls.append((vid_id, f"https://www.instagram.com/reel/{vid_id}/"))
                    app_logger.info(f"Fallback found {len(reel_urls)} entries for @{username}")
        except Exception as e:
            error_logger.error(f"Fallback also failed for @{username}: {e}")

    if not reel_urls:
        error_logger.error(f"Could not find any reels for @{username}. Check cookies and account status.")
        return []

    # ── Step 2: Download each reel individually ──
    dl_opts = {
        "quiet": False,
        "no_warnings": False,
        "ignoreerrors": True,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/mp4/best",
        "merge_output_format": "mp4",
        "retries": 5,
        "fragment_retries": 5,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
            ),
        },
    }
    if cookies_path:
        dl_opts["cookiefile"] = cookies_path
    if proxy:
        dl_opts["proxy"] = proxy

    for vid_id, url in reel_urls[:limit]:
        # Skip if already in DB
        if vid_id and video_exists(vid_id):
            app_logger.info(f"Reel {vid_id} already in DB, skipping.")
            continue

        out_template = str(DOWNLOADS_DIR / f"%(id)s.%(ext)s")
        dl_opts["outtmpl"] = out_template

        try:
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                app_logger.info(f"Downloading reel: {url}")
                info = ydl.extract_info(url, download=True)
                if not info:
                    app_logger.warning(f"No info returned for {url}")
                    continue

                actual_id = info.get("id", vid_id)
                ext = info.get("ext", "mp4")

                # Find the downloaded file
                local_path = str(DOWNLOADS_DIR / f"{actual_id}.{ext}")
                if not os.path.exists(local_path):
                    # Scan for it
                    candidates = list(DOWNLOADS_DIR.glob(f"{actual_id}.*"))
                    candidates = [c for c in candidates if c.suffix in (".mp4", ".mkv", ".webm", ".mov")]
                    if candidates:
                        local_path = str(candidates[0])
                    else:
                        app_logger.warning(f"Could not find downloaded file for {actual_id}")
                        continue

                saved = _save_entry_to_db(info, local_path)
                if saved:
                    downloaded_paths.append(saved)

        except yt_dlp.utils.DownloadError as e:
            error_logger.error(f"DownloadError for {url}: {e}")
        except Exception as e:
            error_logger.error(f"Error downloading {url}: {e}")

    app_logger.info(f"Finished @{username}: {len(downloaded_paths)}/{len(reel_urls)} reels queued.")
    return downloaded_paths


class InstagramWatcher:
    """Monitors Instagram accounts using yt-dlp (replaces blocked instaloader)."""

    def __init__(self):
        pass

    def authenticate(self) -> bool:
        return True

    def check_new_reels(self, max_posts_per_profile: int = 24, proxy: Optional[str] = None) -> List[str]:
        """Scans all active accounts for new reels using yt-dlp."""
        accounts = get_active_accounts()
        if not accounts:
            app_logger.info("No active Instagram accounts to watch.")
            return []

        all_downloaded = []
        for account in accounts:
            app_logger.info(f"Scanning @{account} via yt-dlp...")
            try:
                paths = download_profile_reels(account, limit=max_posts_per_profile, proxy=proxy)
                all_downloaded.extend(paths)
                update_account_checked(account)
            except Exception as e:
                error_logger.error(f"Error scanning @{account}: {e}")

        return all_downloaded
