import os
import pickle
import random
from pathlib import Path
from typing import Optional, List, Any

import google.oauth2.credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from utils import app_logger, error_logger, upload_logger
from config import secrets, load_settings
from database import add_upload, record_upload_failure
from .metadata_generator import generate_shorts_metadata

BASE_DIR = Path(__file__).resolve().parent.parent

# Scope required for uploading videos to YouTube
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]

def get_youtube_service() -> Any:
    """Gets an authorized YouTube API service instance."""
    creds = None
    creds_path = Path(secrets.YOUTUBE_CREDENTIALS_FILE)
    client_secrets_path = Path(secrets.YOUTUBE_CLIENT_SECRETS_FILE)
    
    # Load existing credentials if available
    if creds_path.exists():
        try:
            creds = google.oauth2.credentials.Credentials.from_authorized_user_file(str(creds_path), SCOPES)
        except Exception as e:
            error_logger.error(f"Error loading credentials from file: {e}")
            
    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            app_logger.info("YouTube credentials expired, refreshing...")
            creds.refresh(Request())
            # Save refreshed credentials
            with open(creds_path, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            error_logger.error(f"Failed to refresh YouTube credentials: {e}")
            creds = None
            
    if not creds:
        # Check if secrets file exists to do initial authentication
        if not client_secrets_path.exists():
            error_logger.error(
                f"YouTube client_secrets.json not found at {client_secrets_path}. "
                "Please configure and upload it to authorize the bot."
            )
            return None
            
        app_logger.info("Initializing YouTube OAuth flow...")
        # Note: Local server requires browser. On VPS, credentials must be generated locally 
        # and uploaded, or bot must guide user.
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), SCOPES)
        creds = flow.run_local_server(port=0)
        with open(creds_path, "w") as f:
            f.write(creds.to_json())
            
    return build("youtube", "v3", credentials=creds)

def upload_short(video_id: str, local_path: str, creator: str, original_caption: str) -> Optional[str]:
    """
    Generates AI metadata and uploads a Short to YouTube.
    Saves upload status to SQLite.
    """
    youtube = get_youtube_service()
    if not youtube:
        err_msg = "YouTube service not authorized."
        error_logger.error(err_msg)
        record_upload_failure(video_id, err_msg)
        return None
        
    if not os.path.exists(local_path):
        err_msg = f"Local file not found for upload: {local_path}"
        error_logger.error(err_msg)
        record_upload_failure(video_id, err_msg)
        return None
        
    # Generate metadata (Gemini or Template)
    metadata = generate_shorts_metadata(creator, original_caption)
    title = metadata["title"]
    description = metadata["description"]
    tags_str = metadata["tags"]
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    
    settings = load_settings()
    yt_settings = settings.get("youtube", {})
    category_id = yt_settings.get("category_id", "24")
    privacy = yt_settings.get("privacy_status", "public")
    
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False
        }
    }
    
    upload_logger.info(f"Initiating upload for {video_id}. Title: '{title}'")
    
    try:
        media = MediaFileUpload(
            local_path, 
            chunksize=1024 * 1024 * 1024, # 1GB chunk size (upload in one go)
            resumable=True
        )
        
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                upload_logger.info(f"Uploaded {int(status.progress() * 100)}%...")
                
        youtube_id = response.get("id")
        if youtube_id:
            upload_logger.info(f"Upload complete! YouTube Video ID: {youtube_id}")
            add_upload(youtube_id=youtube_id, video_id=video_id, status="uploaded")
            return youtube_id
        else:
            err_msg = "YouTube response did not contain a video ID."
            error_logger.error(err_msg)
            record_upload_failure(video_id, err_msg)
            return None
            
    except HttpError as e:
        err_msg = f"HTTP Error uploading to YouTube: {e.content.decode() if e.content else e}"
        error_logger.error(err_msg)
        record_upload_failure(video_id, err_msg)
        return None
    except Exception as e:
        err_msg = f"General error uploading to YouTube: {e}"
        error_logger.error(err_msg)
        record_upload_failure(video_id, err_msg)
        return None

def fetch_shorts_analytics(youtube_id: str) -> Optional[dict]:
    """Fetches views, likes, and subscription gain for a uploaded video."""
    youtube = get_youtube_service()
    if not youtube:
        return None
        
    try:
        # Retrieve video statistics
        video_response = youtube.videos().list(
            part="statistics",
            id=youtube_id
        ).execute()
        
        items = video_response.get("items", [])
        if not items:
            return None
            
        stats = items[0]["statistics"]
        return {
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0))
        }
    except Exception as e:
        error_logger.error(f"Error fetching analytics for {youtube_id}: {e}")
        return None
