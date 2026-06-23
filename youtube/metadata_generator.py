import os
import re
import json
import requests
from typing import Dict, Any

from utils import app_logger, error_logger
from config import secrets

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

def clean_title(title: str) -> str:
    """Cleans a title to ensure it fits YouTube Shorts constraints."""
    title = re.sub(r'[^\w\s\-\!\?\#\@]', '', title)  # Remove emojis/symbols that aren't tags/mentions
    title = title.strip()
    if len(title) > 80:  # YouTube max title length is 100, we aim for <80 to leave room for #shorts
        title = title[:77] + "..."
    if "#shorts" not in title.lower():
        title = f"{title} #shorts"
    return title

def generate_metadata_via_gemini(creator: str, caption: str) -> Dict[str, str]:
    """Calls Gemini API to generate engaging Shorts metadata."""
    prompt = (
        f"You are an expert social media manager. I will give you the original creator and "
        f"caption of an Instagram Reel. Please generate a catchy YouTube Shorts title, "
        f"a clean description that credits the original creator, and relevant hashtags.\n\n"
        f"Original Creator: {creator}\n"
        f"Original Caption: {caption}\n\n"
        f"Format your response as a JSON object with keys 'title', 'description', and 'tags' (comma-separated). "
        f"Make sure to include original creator credit in the description. "
        f"Ensure 'title' is under 80 characters and includes '#shorts'. "
        f"Return ONLY valid JSON. No markdown wrappers."
    )
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    url = f"{GEMINI_API_URL}?key={secrets.GEMINI_API_KEY}"
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        res_data = response.json()
        
        # Extract text response from Gemini format
        text_content = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        
        # Clean markdown formatting if present
        text_content = re.sub(r"^```json\s*", "", text_content)
        text_content = re.sub(r"\s*```$", "", text_content)
        
        data = json.loads(text_content)
        
        title = clean_title(data.get("title", f"Reel by @{creator}"))
        description = data.get("description", f"Original video by @{creator}\n\nOriginal caption:\n{caption}")
        tags = data.get("tags", "shorts, viral, trending")
        
        return {
            "title": title,
            "description": description,
            "tags": tags
        }
    except Exception as e:
        error_logger.error(f"Gemini API metadata generation failed: {e}")
        return generate_metadata_fallback(creator, caption)

def generate_metadata_fallback(creator: str, caption: str) -> Dict[str, str]:
    """Generates basic metadata using local templates when Gemini API is unavailable."""
    app_logger.info("Using local template fallback for metadata generation.")
    
    # Extract first sentence/phrase of caption as title
    sentences = re.split(r'[\.\!\?\n]', caption)
    raw_title = sentences[0].strip() if sentences else ""
    
    # If no title could be parsed, use a default
    if not raw_title:
        raw_title = f"Amazing video by @{creator}"
        
    title = clean_title(raw_title)
    
    # Build clean credit-preserving description
    description = (
        f"Credit to original creator: @{creator}\n\n"
        f"Original caption:\n{caption}\n\n"
        f"#shorts #viral #reels #trending"
    )
    
    tags = f"shorts, viral, {creator}, reels, trending"
    
    return {
        "title": title,
        "description": description,
        "tags": tags
    }

def generate_shorts_metadata(creator: str, caption: str) -> Dict[str, str]:
    """Main entry point to generate metadata."""
    if secrets.GEMINI_API_KEY:
        return generate_metadata_via_gemini(creator, caption)
    return generate_metadata_fallback(creator, caption)
