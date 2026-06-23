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
