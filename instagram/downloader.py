import os
import yt_dlp
from pathlib import Path
from typing import Optional, Dict, Any

from utils import app_logger, error_logger, calculate_file_hash, get_video_metadata
from database import add_video, video_exists, file_hash_exists
from config import load_settings

BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

def download_reel(shortcode: str, proxy: Optional[str] = None) -> Optional[str]:
    """
    Downloads an Instagram Reel by shortcode using yt-dlp.
    Validates duration, aspect ratio, resolution, and duplicate hash.
    Saves to database if valid.
    """
    url = f"https://www.instagram.com/reels/{shortcode}/"
    app_logger.info(f"Starting download for Reel: {shortcode} (URL: {url})")
    
    if video_exists(shortcode):
        app_logger.info(f"Reel {shortcode} already exists in database. Skipping download.")
        return None
        
    out_template = str(DOWNLOADS_DIR / f"{shortcode}.%(ext)s")
    
    ydl_opts = {
        'outtmpl': out_template,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        # Allow passing custom headers/user-agent
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    
    if proxy:
        ydl_opts['proxy'] = proxy
        app_logger.info(f"Using proxy for download: {proxy}")
        
    try:
        # Run yt-dlp download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                app_logger.warning(f"Could not extract info for Reel {shortcode}")
                return None
                
            # Locate the actual downloaded file (handling potential extension merges)
            ext = info.get('ext', 'mp4')
            local_path = str(DOWNLOADS_DIR / f"{shortcode}.{ext}")
            
            # Fallback scan in downloads directory if standard path doesn't match
            if not os.path.exists(local_path):
                candidates = list(DOWNLOADS_DIR.glob(f"{shortcode}.*"))
                if candidates:
                    local_path = str(candidates[0])
                else:
                    app_logger.error(f"Downloaded file not found for shortcode: {shortcode}")
                    return None
            
            # 1. Inspect file metadata (ffprobe)
            metadata = get_video_metadata(local_path)
            if not metadata:
                app_logger.warning(f"Failed to retrieve video metadata for {shortcode}. Rejecting.")
                os.remove(local_path)
                return None
                
            # Load threshold rules
            settings = load_settings()
            ig_rules = settings.get("instagram", {})
            min_dur = ig_rules.get("min_duration", 20)
            max_dur = ig_rules.get("max_duration", 60)
            min_h = ig_rules.get("min_height", 720)
            
            duration = metadata["duration"]
            width = metadata["width"]
            height = metadata["height"]
            aspect_ratio = metadata["aspect_ratio"]
            
            # 2. Apply Filters
            # Reject if duration is too short/long
            if not (min_dur <= duration <= max_dur):
                app_logger.warning(f"Reel {shortcode} rejected: Duration {duration:.1f}s not in range [{min_dur}, {max_dur}].")
                os.remove(local_path)
                return None
                
            # Reject if aspect ratio is not vertical (roughly 9:16). Vertical means width < height.
            # Aspect ratio 9/16 = 0.5625. We allow some buffer, but width must be less than height.
            if width >= height:
                app_logger.warning(f"Reel {shortcode} rejected: Not vertical (Dimensions: {width}x{height}, Aspect: {aspect_ratio:.2f}).")
                os.remove(local_path)
                return None
                
            # Reject if resolution is not HD (height < 720)
            if height < min_h:
                app_logger.warning(f"Reel {shortcode} rejected: Quality below HD ({height}p < {min_h}p).")
                os.remove(local_path)
                return None
                
            # 3. Compute hash and check for duplicates
            file_hash = calculate_file_hash(local_path)
            if file_hash_exists(file_hash):
                app_logger.warning(f"Reel {shortcode} rejected: File hash {file_hash} already exists in database (duplicate content).")
                os.remove(local_path)
                return None
                
            # Extract caption and uploader details
            caption = info.get('description', info.get('title', ''))
            creator = info.get('uploader', 'unknown_creator')
            
            # Save to Database
            success = add_video(
                video_id=shortcode,
                creator=creator,
                caption=caption,
                duration=duration,
                file_hash=file_hash,
                local_path=local_path
            )
            
            if success:
                app_logger.info(f"Successfully downloaded and saved Reel: {shortcode}")
                return local_path
            else:
                app_logger.error(f"Failed to write Reel {shortcode} metadata to database.")
                os.remove(local_path)
                return None
                
    except Exception as e:
        error_logger.error(f"Error downloading Reel {shortcode}: {e}")
        return None
