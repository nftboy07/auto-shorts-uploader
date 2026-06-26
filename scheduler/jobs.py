import random
import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from utils import app_logger, error_logger
from config import load_settings
from database import get_upload_queue, get_active_accounts, log_action, get_active_proxies
from instagram import InstagramWatcher
from youtube.uploader import upload_short

# Global scheduler instance
scheduler = AsyncIOScheduler()

async def scan_instagram_job():
    """Job to scan Instagram for new reels."""
    settings = load_settings()
    if settings.get("scheduler", {}).get("paused", False):
        app_logger.info("Scheduler is paused. Skipping Instagram scan.")
        return
        
    # Check and manage disk space before scanning/downloading new videos
    from utils import manage_disk_storage
    await asyncio.to_thread(manage_disk_storage, 5.0)
        
    app_logger.info("Executing periodic Instagram scan...")
    
    proxy = None
    if settings.get("proxy", {}).get("enable_rotation", False):
        active_proxies = get_active_proxies()
        if active_proxies:
            proxy = random.choice(active_proxies)
            app_logger.info(f"Selected active proxy for scan: {proxy}")
            # Dynamically set proxy for requests/urllib inside this scan process
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
        else:
            app_logger.warning("Proxy rotation is enabled, but no active proxies found in database.")
    else:
        # Clear environment variables if proxy is disabled
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)

    watcher = InstagramWatcher()
    
    # Run the watcher check in a separate thread to prevent blocking the async loop
    downloaded = await asyncio.to_thread(watcher.check_new_reels, 24, proxy)
    app_logger.info(f"Instagram scan completed. Downloaded {len(downloaded)} new Reels.")

async def upload_next_from_queue_job():
    """Job that executes every hour to upload the next video in the queue."""
    settings = load_settings()
    if settings.get("scheduler", {}).get("paused", False):
        app_logger.info("Scheduler is paused. Skipping hourly queue upload.")
        return
        
    queue = get_upload_queue()
    if not queue:
        app_logger.info("Upload queue is empty. No video to upload this hour.")
        return
        
    video_item = queue[0]
    video_id = video_item['video_id']
    local_path = video_item['local_path']
    creator = video_item['creator']
    caption = video_item['caption']
    
    app_logger.info(f"Hourly Scheduler: Executing upload for video {video_id}...")
    
    # Run the upload in a separate thread
    youtube_id = await asyncio.to_thread(upload_short, video_id, local_path, creator, caption)
    
    if youtube_id:
        app_logger.info(f"Hourly Scheduler: Successfully uploaded video {video_id} -> YouTube: {youtube_id}")
    else:
        app_logger.error(f"Hourly Scheduler: Failed upload for video {video_id}")

def start_scheduler():
    """Initializes and starts the APScheduler scheduler."""
    settings = load_settings()
    ig_settings = settings.get("instagram", {})
    interval = ig_settings.get("check_interval_seconds", 1800)
    
    # 1. Instagram check job (runs periodically)
    scheduler.add_job(
        scan_instagram_job,
        'interval',
        seconds=interval,
        id='instagram_watcher'
    )
    
    # 2. Hourly upload job (runs every hour at the top of the hour)
    scheduler.add_job(
        upload_next_from_queue_job,
        'cron',
        minute=0,
        id='hourly_uploader'
    )
    
    # Start scheduler
    scheduler.start()
    app_logger.info("APScheduler initialized and started successfully.")
