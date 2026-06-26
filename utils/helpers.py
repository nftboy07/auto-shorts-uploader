import hashlib
import json
import subprocess
import os
from pathlib import Path
from typing import Dict, Any, Optional
from .logger import app_logger, error_logger

def calculate_file_hash(file_path: str) -> str:
    """Calculates the MD5 checksum of a file to detect duplicates."""
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            buf = f.read(65536)
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(65536)
        return hasher.hexdigest()
    except Exception as e:
        error_logger.error(f"Failed to calculate hash for {file_path}: {e}")
        return ""

def get_video_metadata(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Executes ffprobe to extract video metadata.
    Returns a dictionary containing duration, width, height, and aspect ratio.
    """
    if not os.path.exists(file_path):
        error_logger.error(f"Video file does not exist: {file_path}")
        return None
    
    cmd = [
        "ffprobe", 
        "-v", "error", 
        "-print_format", "json", 
        "-show_format", 
        "-show_streams", 
        file_path
    ]
    
    try:
        # Run ffprobe and capture output
        # Set shell=True on Windows to avoid console window flashes if running in background
        result = subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True, 
            check=True
        )
        
        data = json.loads(result.stdout)
        
        # Extract format details
        format_info = data.get("format", {})
        duration = float(format_info.get("duration", 0))
        
        # Find video stream
        video_stream = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break
                
        if not video_stream:
            error_logger.error(f"No video stream found in {file_path}")
            return None
            
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        
        metadata = {
            "duration": duration,
            "width": width,
            "height": height,
            "aspect_ratio": width / height if height > 0 else 0.0
        }
        
        app_logger.info(f"Metadata for {file_path}: {metadata}")
        return metadata
        
    except subprocess.CalledProcessError as e:
        error_logger.error(f"ffprobe failed for {file_path}: {e.stderr}")
        return None
    except Exception as e:
        error_logger.error(f"Exception parsing ffprobe output for {file_path}: {e}")
        return None

def clean_old_files(directory: str, max_age_days: int = 7) -> None:
    """Deletes files in a directory that are older than max_age_days."""
    import time
    dir_path = Path(directory)
    if not dir_path.exists():
        return
        
    now = time.time()
    cutoff = now - (max_age_days * 86400)
    
    for f in dir_path.glob("*"):
        if f.is_file():
            if f.stat().st_mtime < cutoff:
                try:
                    f.unlink()
                    app_logger.info(f"Cleaned up old file: {f}")
                except Exception as e:
                    error_logger.error(f"Failed to delete {f}: {e}")

def extract_thumbnail(video_path: str, output_image_path: str, timestamp_sec: float = 2.0) -> bool:
    """
    Extracts a single high-quality frame from a video at a specific timestamp using FFmpeg
    to serve as a custom YouTube thumbnail.
    """
    if not os.path.exists(video_path):
        error_logger.error(f"Video file does not exist: {video_path}")
        return False
        
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(timestamp_sec),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_image_path
    ]
    
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        app_logger.info(f"Successfully extracted thumbnail from {video_path} to {output_image_path}")
        return True
    except subprocess.CalledProcessError as e:
        error_logger.error(f"FFmpeg thumbnail extraction failed for {video_path}: {e.stderr.decode() if e.stderr else e}")
        return False
    except Exception as e:
        error_logger.error(f"Error during FFmpeg thumbnail extraction: {e}")
        return False

def trim_video(video_path: str, output_path: str, max_duration_sec: float = 60.0) -> bool:
    """
    Trims a video to max_duration_sec using FFmpeg.
    If the video is already within the limit, it copies the file to output_path.
    """
    if not os.path.exists(video_path):
        error_logger.error(f"Video file does not exist: {video_path}")
        return False
        
    metadata = get_video_metadata(video_path)
    if not metadata:
        return False
        
    duration = metadata["duration"]
    if duration <= max_duration_sec:
        import shutil
        try:
            shutil.copy2(video_path, output_path)
            app_logger.info(f"Video {video_path} is within limit ({duration:.1f}s). Copied directly.")
            return True
        except Exception as e:
            error_logger.error(f"Failed to copy video file: {e}")
            return False
            
    # Trim video using FFmpeg and re-encode to guarantee clean metadata and playback sync
    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-t", str(max_duration_sec),
        "-c:v", "libx264",
        "-preset", "superfast",
        "-crf", "22",
        "-c:a", "aac",
        output_path
    ]
    
    try:
        app_logger.info(f"Trimming video {video_path} to {max_duration_sec}s...")
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        app_logger.info(f"Successfully trimmed video to {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        error_logger.error(f"FFmpeg trim failed for {video_path}: {e.stderr.decode() if e.stderr else e}")
        return False
    except Exception as e:
        error_logger.error(f"Error during FFmpeg trim: {e}")
        return False

def manage_disk_storage(min_free_gb: float = 5.0) -> None:
    """
    Checks free disk space. If free space is less than min_free_gb,
    it deletes the oldest uploaded video files from the filesystem
    until free space is above the threshold.
    """
    import shutil
    import database as db
    
    path_to_check = str(Path(__file__).resolve().parent.parent)
    try:
        usage = shutil.disk_usage(path_to_check)
        free_gb = usage.free / (1024 ** 3)
        app_logger.info(f"Disk storage check: {free_gb:.2f} GB free.")
        
        if free_gb >= min_free_gb:
            return
            
        app_logger.warning(f"Free disk space ({free_gb:.2f} GB) is below threshold ({min_free_gb} GB). Cleaning up old uploaded files...")
        
        # Query database for uploaded videos, oldest first
        with db.db_session() as conn:
            uploaded_videos = conn.execute(
                "SELECT video_id, local_path FROM videos WHERE status = 'uploaded' ORDER BY download_date ASC"
            ).fetchall()
            
        deleted_count = 0
        for row in uploaded_videos:
            video_id = row["video_id"]
            local_path = row["local_path"]
            
            if local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                    deleted_count += 1
                    app_logger.info(f"Deleted uploaded video file to free space: {local_path}")
                except Exception as e:
                    error_logger.error(f"Failed to delete {local_path}: {e}")
                    
            # Update database status to mark it as cleaned (and local_path to NULL)
            with db.db_session() as conn:
                conn.execute(
                    "UPDATE videos SET status = 'cleaned', local_path = NULL WHERE video_id = ?",
                    (video_id,)
                )
                
            # Recheck disk space
            usage = shutil.disk_usage(path_to_check)
            free_gb = usage.free / (1024 ** 3)
            if free_gb >= min_free_gb:
                app_logger.info(f"Free disk space recovered to {free_gb:.2f} GB. Stopping cleanup.")
                break
                
        app_logger.info(f"Disk storage cleanup finished. Deleted {deleted_count} video files.")
    except Exception as e:
        error_logger.error(f"Error during disk storage cleanup: {e}")

import re

def extract_instagram_username(input_str: str) -> str:
    """
    Extracts the clean Instagram username from a username string,
    an @username format, or a profile URL.
    """
    input_str = input_str.strip()
    if input_str.startswith('@'):
        input_str = input_str[1:]
    
    # Matches URLs like https://www.instagram.com/username?igsh=...
    match = re.search(r'(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_\.]+)', input_str, re.IGNORECASE)
    if match:
        return match.group(1).lower()
        
    return input_str.lower()

