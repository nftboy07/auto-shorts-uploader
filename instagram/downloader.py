import os
import yt_dlp
from pathlib import Path
from typing import Optional, Dict, Any

from utils import app_logger, error_logger, calculate_file_hash, get_video_metadata, trim_video
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
                
            duration = metadata["duration"]
            
            # 2. Trim video if it exceeds 60 seconds (YouTube Shorts limit)
            if duration > 60.0:
                app_logger.info(f"Video {shortcode} duration {duration:.1f}s exceeds 60s. Trimming to 60s...")
                temp_trimmed_path = str(DOWNLOADS_DIR / f"{shortcode}_trimmed.mp4")
                if trim_video(local_path, temp_trimmed_path, 60.0):
                    # Replace original file with the trimmed file
                    os.remove(local_path)
                    os.rename(temp_trimmed_path, local_path)
                    
                    # Re-inspect metadata of the trimmed video
                    metadata = get_video_metadata(local_path)
                    if not metadata:
                        app_logger.warning(f"Failed to retrieve metadata for trimmed video {shortcode}. Rejecting.")
                        return None
                    duration = metadata["duration"]
                else:
                    app_logger.warning(f"Failed to trim video {shortcode}. Rejecting.")
                    os.remove(local_path)
                    return None
                
            # 3. Compute hash and check for duplicates to prevent double-uploading
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
