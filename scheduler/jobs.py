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
    downloaded = await asyncio.to_thread(watcher.check_new_reels, 5, proxy)
    app_logger.info(f"Instagram scan completed. Downloaded {len(downloaded)} new Reels.")

async def perform_scheduled_upload(video_id: str, local_path: str, creator: str, caption: str):
    """Job that executes an individual video upload."""
    settings = load_settings()
    if settings.get("scheduler", {}).get("paused", False):
        app_logger.info(f"Scheduler is paused. Postponing upload of video: {video_id}")
        return
        
    app_logger.info(f"Executing scheduled upload for video {video_id}...")
    
    # Run the upload in a separate thread
    youtube_id = await asyncio.to_thread(upload_short, video_id, local_path, creator, caption)
    
    if youtube_id:
        app_logger.info(f"Successfully uploaded scheduled video {video_id} -> YouTube: {youtube_id}")
    else:
        app_logger.error(f"Failed scheduled upload for video {video_id}")

def generate_random_slots(count: int) -> List[datetime]:
    """Generates 'count' random datetimes spread across the next 24 hours, avoiding bursts."""
    now = datetime.now()
    slots = []
    
    # Distribute times slots by dividing the 24 hour block into equal windows, then adding jitter
    window_hours = 24.0 / count
    
    for i in range(count):
        window_start = now + timedelta(hours=i * window_hours)
        # Add random jitter within the window (keep at least 15 mins padding from window bounds)
        jitter_minutes = random.uniform(15, (window_hours * 60) - 15)
        slot_time = window_start + timedelta(minutes=jitter_minutes)
        slots.append(slot_time)
        
    return slots

async def plan_daily_uploads_job():
    """
    Job that runs daily at midnight to calculate the randomized upload schedule for the day.
    Schedules one-off upload tasks.
    """
    settings = load_settings()
    if settings.get("scheduler", {}).get("paused", False):
        app_logger.info("Scheduler is paused. Skipping daily upload planning.")
        return
        
    yt_settings = settings.get("youtube", {})
    min_uploads = yt_settings.get("min_uploads_per_day", 8)
    max_uploads = yt_settings.get("max_uploads_per_day", 20)
    
    upload_count = random.randint(min_uploads, max_uploads)
    app_logger.info(f"Planning {upload_count} randomized uploads for the next 24 hours...")
    
    queue = get_upload_queue()
    if not queue:
        app_logger.warning("Upload queue is empty. Cannot schedule any uploads today.")
        return
        
    # Generate schedule times slots
    slot_times = generate_random_slots(upload_count)
    
    # Match schedule slots with items in queue
    scheduled_count = 0
    for i, slot_time in enumerate(slot_times):
        if i >= len(queue):
            break
            
        video_item = queue[i]
        video_id = video_item['video_id']
        local_path = video_item['local_path']
        creator = video_item['creator']
        caption = video_item['caption']
        
        # Schedule the job
        job_id = f"upload_{video_id}_{slot_time.strftime('%Y%m%d%H%M%S')}"
        scheduler.add_job(
            perform_scheduled_upload,
            DateTrigger(run_date=slot_time),
            id=job_id,
            args=[video_id, local_path, creator, caption]
        )
        
        log_action("schedule_upload", f"Scheduled video {video_id} for upload at {slot_time.strftime('%H:%M:%S')}")
        scheduled_count += 1
        
    app_logger.info(f"Scheduled {scheduled_count} uploads out of {upload_count} target slots.")

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
    
    # 2. Daily planning job (runs every day at midnight)
    scheduler.add_job(
        plan_daily_uploads_job,
        'cron',
        hour=0,
        minute=0,
        id='daily_planner'
    )
    
    # Start scheduler
    scheduler.start()
    app_logger.info("APScheduler initialized and started successfully.")
    
    # Run initial planning on startup
    scheduler.add_job(
        plan_daily_uploads_job,
        DateTrigger(run_date=datetime.now() + timedelta(seconds=5)),
        id='startup_planner'
    )
