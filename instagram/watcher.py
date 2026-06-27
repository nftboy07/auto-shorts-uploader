"""
Instagram watcher using a two-stage approach:
  1. Instagram private mobile API  →  get list of reel shortcodes
  2. yt-dlp                        →  download each individual reel URL

This avoids yt-dlp's broken profile-page extractor (which returns 0 results
because Instagram's /reels/ page is JavaScript-rendered).
"""
import os
import re
import json
import time
import http.cookiejar
import urllib.request
import urllib.error
import yt_dlp
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from utils import app_logger, error_logger
from database import get_active_accounts, update_account_checked, video_exists, add_video, file_hash_exists
from utils import calculate_file_hash, get_video_metadata, trim_video
from config import load_settings

BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Instagram private API constants (mobile app IDs — well-known public values)
IG_APP_ID = "936619743392459"
IG_API_BASE = "https://i.instagram.com/api/v1"
IG_USER_AGENT = (
    "Instagram 275.0.0.27.98 Android (33/13; 420dpi; 1080x2400; "
    "samsung; SM-G991B; o1s; exynos2100; en_US; 458229258)"
)


# ─────────────────────────────────────────────────────────────────────────────
# Cookie helpers
# ─────────────────────────────────────────────────────────────────────────────

def _find_cookies_path() -> Optional[str]:
    """Return the first valid Instagram Netscape-format cookies file."""
    candidates = [
        str(BASE_DIR / "config" / "instagram_cookies.txt"),
        str(BASE_DIR / "instagram_cookies.txt"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                content = open(path).read()
                if "instagram.com" in content and "sessionid" in content:
                    app_logger.info(f"Valid cookies file: {path}")
                    return path
                else:
                    app_logger.warning(f"Cookies at {path} missing sessionid")
            except Exception as e:
                app_logger.warning(f"Cannot read {path}: {e}")
    app_logger.warning("No valid Instagram cookies file found")
    return None


def _parse_cookies(cookies_path: str) -> Dict[str, str]:
    """Parse Netscape cookie file and return a dict of name→value for instagram.com."""
    cookies: Dict[str, str] = {}
    try:
        with open(cookies_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7 and "instagram.com" in parts[0]:
                    name, value = parts[5], parts[6]
                    cookies[name] = value
    except Exception as e:
        error_logger.error(f"Failed to parse cookies from {cookies_path}: {e}")
    return cookies


def _cookie_header(cookies: Dict[str, str]) -> str:
    """Build Cookie: header string from dict."""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


# ─────────────────────────────────────────────────────────────────────────────
# Instagram private API — get user ID + reel list
# ─────────────────────────────────────────────────────────────────────────────

def _api_request(url: str, cookies: Dict[str, str], proxy: Optional[str] = None) -> Optional[dict]:
    """Make an authenticated request to the Instagram private API."""
    headers = {
        "User-Agent": IG_USER_AGENT,
        "X-IG-App-ID": IG_APP_ID,
        "X-IG-Capabilities": "3brTvw==",
        "X-IG-Connection-Type": "WIFI",
        "Accept-Language": "en-US",
        "Cookie": _cookie_header(cookies),
    }
    req = urllib.request.Request(url, headers=headers)

    if proxy:
        proxy_handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        opener = urllib.request.build_opener(proxy_handler)
    else:
        opener = urllib.request.build_opener()

    try:
        with opener.open(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except urllib.error.HTTPError as e:
        error_logger.error(f"API HTTP {e.code} for {url}: {e.read()[:300].decode(errors='replace')}")
    except Exception as e:
        error_logger.error(f"API request failed for {url}: {e}")
    return None


def _get_user_id(username: str, cookies: Dict[str, str], proxy: Optional[str] = None) -> Optional[str]:
    """Resolve Instagram username → numeric user ID via web_profile_info API."""
    url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
    data = _api_request(url, cookies, proxy)
    if data:
        try:
            user_id = data["data"]["user"]["id"]
            app_logger.info(f"Resolved @{username} → user_id={user_id}")
            return str(user_id)
        except (KeyError, TypeError) as e:
            error_logger.error(f"Could not parse user_id for @{username}: {e} | response: {str(data)[:300]}")
    return None


def _get_reels_from_api(user_id: str, username: str, cookies: Dict[str, str],
                         limit: int = 24, proxy: Optional[str] = None) -> List[Tuple[str, str]]:
    """
    Fetch reel shortcodes from Instagram API.
    Returns list of (shortcode, url) tuples.
    """
    results: List[Tuple[str, str]] = []
    max_id = None

    while len(results) < limit:
        url = f"{IG_API_BASE}/clips/user/?target_user_id={user_id}&page_size=12"
        if max_id:
            url += f"&max_id={max_id}"

        data = _api_request(url, cookies, proxy)
        if not data:
            break

        items = data.get("items", [])
        if not items:
            app_logger.info(f"No more reels from API for @{username}")
            break

        for item in items:
            media = item.get("media", item)
            code = media.get("code") or media.get("shortcode")
            media_id = media.get("pk") or media.get("id")
            media_type = media.get("media_type", 0)

            # media_type 2 = VIDEO, clips always video
            if not code and not media_id:
                continue

            reel_url = f"https://www.instagram.com/reel/{code}/" if code else None
            if reel_url and (code, reel_url) not in results:
                results.append((code or str(media_id), reel_url))
                if len(results) >= limit:
                    break

        # Pagination
        paging = data.get("paging_info") or {}
        more = paging.get("more_available", False)
        max_id = paging.get("max_id")
        if not more or not max_id:
            break
        time.sleep(0.5)

    app_logger.info(f"API returned {len(results)} reel URLs for @{username}")
    return results[:limit]


def _get_reels_fallback_feed(user_id: str, username: str, cookies: Dict[str, str],
                               limit: int = 24, proxy: Optional[str] = None) -> List[Tuple[str, str]]:
    """Fallback: use user feed API to find video posts."""
    results: List[Tuple[str, str]] = []
    url = f"{IG_API_BASE}/feed/user/{user_id}/?count={limit}"
    data = _api_request(url, cookies, proxy)
    if not data:
        return results
    for item in data.get("items", []):
        if item.get("media_type") != 2:  # 2 = video
            continue
        code = item.get("code") or item.get("shortcode")
        if code:
            results.append((code, f"https://www.instagram.com/reel/{code}/"))
        if len(results) >= limit:
            break
    app_logger.info(f"Feed fallback returned {len(results)} videos for @{username}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# yt-dlp download + DB save
# ─────────────────────────────────────────────────────────────────────────────

def _ydl_opts(cookies_path: Optional[str], proxy: Optional[str]) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/mp4/best",
        "merge_output_format": "mp4",
        "outtmpl": str(DOWNLOADS_DIR / "%(id)s.%(ext)s"),
        "retries": 5,
        "fragment_retries": 5,
        "http_headers": {
            "User-Agent": IG_USER_AGENT,
        },
    }
    if cookies_path:
        opts["cookiefile"] = cookies_path
    if proxy:
        opts["proxy"] = proxy
    return opts


def _save_to_db(info: Dict[str, Any], local_path: str) -> Optional[str]:
    """Validate downloaded file and add to the upload queue. Returns path or None."""
    video_id = info.get("id", "")
    uploader = (info.get("uploader") or info.get("uploader_id")
                or info.get("channel") or "unknown")
    caption = (info.get("description") or info.get("title")
               or f"Reel by @{uploader}")

    if not os.path.exists(local_path):
        error_logger.error(f"File missing after download: {local_path}")
        return None

    if video_exists(video_id):
        app_logger.info(f"Reel {video_id} already in DB, skipping")
        try:
            os.remove(local_path)
        except Exception:
            pass
        return None

    metadata = get_video_metadata(local_path)
    if not metadata:
        app_logger.warning(f"ffprobe failed for {video_id}, skipping")
        try:
            os.remove(local_path)
        except Exception:
            pass
        return None

    duration = metadata["duration"]

    if duration > 60.0:
        trimmed = str(DOWNLOADS_DIR / f"{video_id}_trimmed.mp4")
        app_logger.info(f"Trimming {video_id} ({duration:.1f}s → 60s)")
        if trim_video(local_path, trimmed, 60.0):
            try:
                os.remove(local_path)
            except Exception:
                pass
            local_path = trimmed
            metadata = get_video_metadata(local_path)
            if not metadata:
                return None
            duration = metadata["duration"]
        else:
            try:
                os.remove(local_path)
            except Exception:
                pass
            return None

    file_hash = calculate_file_hash(local_path)
    if file_hash_exists(file_hash):
        app_logger.warning(f"Duplicate content for {video_id}, skipping")
        try:
            os.remove(local_path)
        except Exception:
            pass
        return None

    if add_video(video_id=video_id, creator=uploader, caption=caption[:500],
                 duration=duration, file_hash=file_hash, local_path=local_path):
        app_logger.info(f"Queued: {video_id} by @{uploader} ({duration:.1f}s)")
        return local_path

    error_logger.error(f"DB insert failed for {video_id}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def download_profile_reels(username: str, limit: int = 24,
                            proxy: Optional[str] = None) -> List[str]:
    """
    Download the latest `limit` reels from an Instagram profile.

    Stage 1 – Instagram private mobile API → list of individual reel URLs
    Stage 2 – yt-dlp → download each URL
    """
    app_logger.info(f"Starting reel download for @{username} (limit={limit})")

    cookies_path = _find_cookies_path()
    if not cookies_path:
        error_logger.error(
            "No Instagram cookies found. "
            "Add INSTAGRAM_COOKIES secret in GitHub → re-deploy."
        )
        return []

    cookies = _parse_cookies(cookies_path)
    if not cookies.get("sessionid"):
        error_logger.error("sessionid not found in cookies file. Re-export your cookies.")
        return []

    # ── Stage 1: get reel URLs via private API ──────────────────────────────
    user_id = _get_user_id(username, cookies, proxy)
    if not user_id:
        error_logger.error(
            f"Could not resolve user_id for @{username}. "
            "Account may be private, suspended, or cookies expired."
        )
        return []

    reel_pairs = _get_reels_from_api(user_id, username, cookies, limit, proxy)
    if not reel_pairs:
        app_logger.info(f"Clips API returned 0 results for @{username}, trying feed fallback")
        reel_pairs = _get_reels_fallback_feed(user_id, username, cookies, limit, proxy)

    if not reel_pairs:
        error_logger.error(
            f"Zero reels found via API for @{username}. "
            "Account may have no public reels or cookies are invalid."
        )
        return []

    # ── Stage 2: download each URL with yt-dlp ─────────────────────────────
    opts = _ydl_opts(cookies_path, proxy)
    downloaded: List[str] = []

    for shortcode, reel_url in reel_pairs:
        if video_exists(shortcode):
            app_logger.info(f"Already in DB: {shortcode}")
            continue

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                app_logger.info(f"Downloading: {reel_url}")
                info = ydl.extract_info(reel_url, download=True)
                if not info:
                    app_logger.warning(f"yt-dlp returned no info for {reel_url}")
                    continue

                vid_id = info.get("id", shortcode)
                ext = info.get("ext", "mp4")
                local_path = str(DOWNLOADS_DIR / f"{vid_id}.{ext}")

                if not os.path.exists(local_path):
                    candidates = [
                        c for c in DOWNLOADS_DIR.glob(f"{vid_id}.*")
                        if c.suffix in (".mp4", ".mkv", ".webm", ".mov")
                    ]
                    if candidates:
                        local_path = str(candidates[0])
                    else:
                        app_logger.warning(f"Downloaded file not found for {vid_id}")
                        continue

                saved = _save_to_db(info, local_path)
                if saved:
                    downloaded.append(saved)

        except yt_dlp.utils.DownloadError as e:
            error_logger.error(f"yt-dlp DownloadError for {reel_url}: {e}")
        except Exception as e:
            error_logger.error(f"Unexpected error for {reel_url}: {e}")

    app_logger.info(
        f"Finished @{username}: {len(downloaded)}/{len(reel_pairs)} reels queued"
    )
    return downloaded


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler watcher class
# ─────────────────────────────────────────────────────────────────────────────

class InstagramWatcher:
    """Periodic watcher — called by APScheduler every N minutes."""

    def authenticate(self) -> bool:
        return True

    def check_new_reels(self, max_posts_per_profile: int = 24,
                        proxy: Optional[str] = None) -> List[str]:
        accounts = get_active_accounts()
        if not accounts:
            app_logger.info("No active Instagram accounts to watch.")
            return []

        all_downloaded: List[str] = []
        for account in accounts:
            app_logger.info(f"Scanning Instagram account via yt-dlp: @{account}")
            try:
                paths = download_profile_reels(account, limit=max_posts_per_profile,
                                               proxy=proxy)
                all_downloaded.extend(paths)
                update_account_checked(account)
            except Exception as e:
                error_logger.error(f"Error scanning @{account}: {e}")

        return all_downloaded
