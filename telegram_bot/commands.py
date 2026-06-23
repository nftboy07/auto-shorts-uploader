import os
import subprocess
import sys
import psutil
import re
import asyncio
import instaloader
from pathlib import Path
from datetime import datetime
from typing import List

from telegram import Update
from telegram.ext import ContextTypes

from config import load_settings, save_settings, secrets
from utils import app_logger, error_logger, get_latest_logs
import database as db

BASE_DIR = Path(__file__).resolve().parent.parent

def admin_only(func):
    """Decorator to restrict commands to admin users only."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        settings = load_settings()
        allowed = settings.get("telegram", {}).get("allowed_admins", [])
        
        # Auto-register first user as admin if empty
        if not allowed:
            allowed.append(user_id)
            if "telegram" not in settings:
                settings["telegram"] = {}
            settings["telegram"]["allowed_admins"] = allowed
            save_settings(settings)
            await update.message.reply_text(f"No admin registered. You have been auto-registered as Admin (ID: {user_id}).")
            return await func(update, context, *args, **kwargs)
            
        if user_id not in allowed:
            app_logger.warning(f"Unauthorized access attempt by user {user_id} (@{update.effective_user.username})")
            await update.message.reply_text("❌ Unauthorized: This command is restricted to administrators.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- General Commands ---

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Greets the user and lists available commands."""
    msg = (
        "🤖 **Instagram → YouTube Shorts Agent**\n\n"
        "Available Commands:\n"
        "📈 `/status` - Bot & Queue Status\n"
        "🏥 `/health` - System health check\n"
        "📜 `/logs` - App log snippets\n"
        "📋 `/queue` - Downloaded Reels pending upload\n"
        "🎥 `/lastupload` - Details of last uploaded video\n"
        "⚡ `/upload_now` - Upload next in queue immediately\n"
        "👤 `/accounts` - Monitor list\n"
        "➕ `/add_account <user>` - Add IG profile\n"
        "➖ `/remove_account <user>` - Remove IG profile\n"
        "🌐 `/proxies` - Registered proxies\n"
        "📊 `/stats` - Analytics report\n"
        "🔄 `/update` - Pull code & restart bot\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays current system status, account counts, and queue statistics."""
    accounts = db.list_accounts()
    queue = db.get_upload_queue()
    proxies = db.get_all_proxies()
    
    settings = load_settings()
    is_paused = settings.get("scheduler", {}).get("paused", False)
    
    status_str = (
        f"🤖 **Bot Status:** {'⏸ PAUSED' if is_paused else '▶ RUNNING'}\n"
        f"👥 **Monitored IG Accounts:** {len(accounts)} total ({len([a for a in accounts if a['is_active']])} active)\n"
        f"📦 **Queue Size (Downloaded Reels):** {len(queue)} videos pending upload\n"
        f"🌐 **Proxies Configured:** {len(proxies)} total ({len([p for p in proxies if p['status'] == 'active'])} active)\n"
    )
    await update.message.reply_text(status_str, parse_mode="Markdown")

async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Performs a diagnostics health check."""
    db_ok = "OK"
    try:
        db.get_active_accounts()
    except Exception as e:
        db_ok = f"ERROR: {e}"
        
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    
    msg = (
        f"🏥 **System Health Check:**\n\n"
        f"🗄 **SQLite DB:** {db_ok}\n"
        f"💻 **CPU Usage:** {cpu}%\n"
        f"🧠 **RAM Usage:** {ram}%\n"
        f"💾 **Disk Space:** {disk}%\n"
        f"⏰ **Current Server Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Returns the latest logs from app.log."""
    logs = get_latest_logs("app.log", 50)
    if len(logs) > 4000:
        logs = logs[-4000:]
    await update.message.reply_text(f"```\n{logs}\n```", parse_mode="Markdown")

async def lastupload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays information on the last uploaded video."""
    last = db.get_last_upload()
    if not last:
        await update.message.reply_text("No uploads recorded in database yet.")
        return
        
    msg = (
        f"🎥 **Last YouTube Upload:**\n\n"
        f"🔗 **YouTube Link:** https://youtu.be/{last['youtube_id']}\n"
        f"🆔 **Video ID:** `{last['video_id']}`\n"
        f"👤 **Creator:** @{last['creator']}\n"
        f"⏰ **Upload Time:** {last['upload_time']}\n"
        f"💬 **Caption:** {last['caption'][:100] if last['caption'] else 'None'}..."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows all files currently queued for upload."""
    queue = db.get_upload_queue()
    if not queue:
        await update.message.reply_text("Upload queue is empty. No new Reels downloaded.")
        return
        
    msg = "📋 **Upload Queue:**\n\n"
    for idx, item in enumerate(queue[:15], 1):
        msg += f"{idx}. `{item['video_id']}` by @{item['creator']} ({int(item['duration'])}s) - downloaded {item['download_date'][:16]}\n"
        
    if len(queue) > 15:
        msg += f"\n... and {len(queue) - 15} more in queue."
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def accounts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists watched accounts."""
    accounts = db.list_accounts()
    if not accounts:
        await update.message.reply_text("No Instagram accounts are monitored. Use `/add_account <username>`.")
        return
        
    msg = "👥 **Monitored Instagram Accounts:**\n\n"
    for acc in accounts:
        status = "✅ Active" if acc['is_active'] else "❌ Inactive"
        checked = acc['last_checked'][:16] if acc['last_checked'] else "Never"
        msg += f"• @{acc['username']} | {status} | Checked: {checked}\n"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def download_and_upload_recent_reels(username: str, limit: int = 5, update: Update = None):
    """Downloads and uploads the last 'limit' reels from a profile immediately."""
    from instagram.downloader import download_reel
    from youtube.uploader import upload_short
    
    if update:
        await update.message.reply_text(f"⏳ Scanning @{username} for the latest {limit} Reels...")
        
    # We will instantiate a new Instaloader watcher
    from instagram.watcher import InstagramWatcher
    watcher = InstagramWatcher()
    
    def run_check():
        watcher.authenticate()
        try:
            profile = instaloader.Profile.from_username(watcher.loader.context, username)
            downloaded = []
            count = 0
            for post in profile.get_posts():
                if count >= limit:
                    break
                if post.is_video:
                    shortcode = post.shortcode
                    if not db.video_exists(shortcode):
                        local_path = download_reel(shortcode)
                        if local_path:
                            downloaded.append((shortcode, local_path, post.owner_username, post.caption or ""))
                    count += 1
            return downloaded
        except Exception as e:
            error_logger.error(f"Error checking profile @{username} on addition: {e}")
            return []
            
    downloaded_items = await asyncio.to_thread(run_check)
    
    if not downloaded_items:
        if update:
            await update.message.reply_text(f"ℹ️ No new/valid Reels found on @{username} to upload.")
        return
        
    if update:
        await update.message.reply_text(f"📥 Downloaded {len(downloaded_items)} Reels. Starting uploads...")
        
    for shortcode, local_path, creator, caption in downloaded_items:
        if update:
            await update.message.reply_text(f"🚀 Uploading `{shortcode}` by @{creator} to YouTube Shorts...")
            
        youtube_id = await asyncio.to_thread(upload_short, shortcode, local_path, creator, caption)
        
        if youtube_id:
            if update:
                await update.message.reply_text(f"✅ Succeeded: `{shortcode}` -> https://youtu.be/{youtube_id}")
        else:
            if update:
                await update.message.reply_text(f"❌ Failed to upload `{shortcode}`.")

async def add_account_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adds a new Instagram account to watch and downloads/uploads last 5 videos."""
    if not context.args:
        await update.message.reply_text("Usage: `/add_account <instagram_username>`")
        return
        
    username = context.args[0].strip().lower()
    if db.add_account(username):
        await update.message.reply_text(f"✅ Added account @{username} to watchlist.")
        # Trigger background task for immediate 5 reels download and upload
        asyncio.create_task(download_and_upload_recent_reels(username, limit=5, update=update))
    else:
        await update.message.reply_text(f"❌ Failed to add account @{username}.")

async def remove_account_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Removes an Instagram account from watchlist."""
    if not context.args:
        await update.message.reply_text("Usage: `/remove_account <instagram_username>`")
        return
        
    username = context.args[0]
    if db.remove_account(username):
        await update.message.reply_text(f"✅ Removed account @{username} from watchlist.")
    else:
        await update.message.reply_text(f"❌ Failed to remove account @{username}.")

async def upload_now_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Triggers an immediate upload of the first video in the queue."""
    queue = db.get_upload_queue()
    if not queue:
        await update.message.reply_text("❌ Queue is empty. Nothing to upload.")
        return
        
    item = queue[0]
    video_id = item['video_id']
    local_path = item['local_path']
    creator = item['creator']
    caption = item['caption']
    
    await update.message.reply_text(f"⚡ Forcing upload for `{video_id}` by @{creator}...")
    
    # Run the upload logic synchronously in a thread pool to avoid blocking the bot event loop
    import asyncio
    from youtube.uploader import upload_short
    
    youtube_id = await asyncio.to_thread(upload_short, video_id, local_path, creator, caption)
    
    if youtube_id:
        await update.message.reply_text(f"✅ Upload succeeded! Video Link: https://youtu.be/{youtube_id}")
    else:
        await update.message.reply_text(f"❌ Upload failed. Check `/logs` for details.")

async def pause_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pauses the scheduler."""
    settings = load_settings()
    if "scheduler" not in settings:
        settings["scheduler"] = {}
    settings["scheduler"]["paused"] = True
    save_settings(settings)
    await update.message.reply_text("⏸ Scheduler paused. Automated checks and uploads are suspended.")

async def resume_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resumes the scheduler."""
    settings = load_settings()
    if "scheduler" not in settings:
        settings["scheduler"] = {}
    settings["scheduler"]["paused"] = False
    save_settings(settings)
    await update.message.reply_text("▶ Scheduler resumed. Automated processes are active.")

async def proxies_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists proxies."""
    proxies = db.get_all_proxies()
    if not proxies:
        await update.message.reply_text("No proxies registered. Use `/add_proxy`.")
        return
        
    msg = "🌐 **Configured Proxies:**\n\n"
    for p in proxies:
        status = "✅ Active" if p['status'] == 'active' else "❌ Inactive"
        msg += f"• `{p['proxy_url']}` | {status} | Failures: {p['failure_count']}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def add_proxy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adds a proxy URL."""
    if not context.args:
        await update.message.reply_text("Usage: `/add_proxy <proxy_url>`\nExample: `http://user:pass@ip:port`")
        return
    url = context.args[0]
    if db.add_proxy(url):
        await update.message.reply_text(f"✅ Added proxy: `{url}`")
    else:
        await update.message.reply_text("❌ Failed to add proxy.")

async def remove_proxy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Removes a proxy URL."""
    if not context.args:
        await update.message.reply_text("Usage: `/remove_proxy <proxy_url>`")
        return
    url = context.args[0]
    if db.remove_proxy(url):
        await update.message.reply_text(f"✅ Removed proxy: `{url}`")
    else:
        await update.message.reply_text("❌ Failed to remove proxy.")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Aggregates analytics report."""
    analytics = db.get_analytics_summary()
    if not analytics:
        await update.message.reply_text("No daily metrics stored yet.")
        return
        
    msg = "📊 **YouTube Shorts Analytics (Last 7 Days):**\n\n"
    for day in analytics[:7]:
        msg += (
            f"📅 **Date:** {day['date']}\n"
            f"🎬 Uploads: {day['videos_uploaded']} | 👁 Views: {day['views']}\n"
            f"👍 Likes: {day['likes']} | 👥 Subs Gained: {day['subs_gained']}\n\n"
        )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays last 15 items in action history."""
    hist = db.get_system_history(15)
    if not hist:
        await update.message.reply_text("No actions recorded in history.")
        return
    msg = "📜 **Bot Operation History:**\n\n"
    for item in hist:
        msg += f"[{item['timestamp'][:16]}] **{item['action'].upper()}**: {item['details']}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pulls code changes from Git and restarts the bot process."""
    await update.message.reply_text("🔄 Initiating update. Pulling codebase from git...")
    try:
        # Run git pull
        result = subprocess.run(["git", "pull"], cwd=str(BASE_DIR), capture_output=True, text=True)
        await update.message.reply_text(f"Git output:\n```\n{result.stdout}\n```", parse_mode="Markdown")
        
        # Install requirements
        pip_res = subprocess.run(["pip", "install", "-r", "requirements.txt"], cwd=str(BASE_DIR), capture_output=True, text=True)
        await update.message.reply_text("Packages updated. Restarting bot process...")
        
        # Restart bot (will be caught by Systemd or Docker restarts)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        await update.message.reply_text(f"❌ Update failed: {e}")

# --- Admin Only Commands ---

@admin_only
async def shell_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Executes a command inside the server shell (strictly restricted)."""
    if not context.args:
        await update.message.reply_text("Usage: `/shell <command>`")
        return
        
    cmd_str = " ".join(context.args)
    await update.message.reply_text(f"🐚 Executing: `{cmd_str}`...")
    
    try:
        res = subprocess.run(cmd_str, shell=True, capture_output=True, text=True, timeout=30)
        out = res.stdout if res.stdout else ""
        err = res.stderr if res.stderr else ""
        await update.message.reply_text(f"Stdout:\n```\n{out}\n```\nStderr:\n```\n{err}\n```", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Execution failed: {e}")

@admin_only
async def system_info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Returns detailed OS system info."""
    import platform
    import time
    
    boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    uptime = str(datetime.now() - datetime.fromtimestamp(psutil.boot_time())).split('.')[0]
    
    msg = (
        f"💻 **Server System Info:**\n\n"
        f"🖥 **OS:** {platform.system()} {platform.release()}\n"
        f"📈 **Architecture:** {platform.machine()}\n"
        f"⏱ **System Uptime:** {uptime} (Booted: {boot_time})\n"
        f"📂 **Current Folder:** `{BASE_DIR}`\n"
        f"🐍 **Python version:** {platform.python_version()}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def upload_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses a shared Instagram Reel link, downloads it, and uploads it to YouTube Shorts immediately."""
    text = update.message.text.strip() if update.message.text else ""
    
    # Check for command structure or direct URL
    match = re.search(r'instagram\.com/(?:reel|reels|p)/([A-Za-z0-9_\-]+)', text)
    if not match and context.args:
        text = context.args[0]
        match = re.search(r'instagram\.com/(?:reel|reels|p)/([A-Za-z0-9_\-]+)', text)
        
    if not match:
        if text.startswith('/upload_url'):
            await update.message.reply_text("❌ Invalid link format. Usage: `/upload_url <instagram_url>`")
        return
        
    # Check authorization
    user_id = update.effective_user.id
    settings = load_settings()
    allowed = settings.get("telegram", {}).get("allowed_admins", [])
    if user_id not in allowed:
        return  # Ignore unauthorized users
        
    shortcode = match.group(1)
    await update.message.reply_text(f"⚡ Instagram Reel link detected (Shortcode: `{shortcode}`). Downloading...")
    
    from instagram.downloader import download_reel
    from youtube.uploader import upload_short
    
    # Download in thread pool
    local_path = await asyncio.to_thread(download_reel, shortcode)
    
    if not local_path:
        await update.message.reply_text("❌ Download failed. File might be a duplicate, not vertical, or outside 20-60s limit.")
        return
        
    # Query database to retrieve metadata extracted by downloader
    with db.db_session() as conn:
        row = conn.execute("SELECT creator, caption FROM videos WHERE video_id = ?", (shortcode,)).fetchone()
        
    creator = row["creator"] if row else "unknown"
    caption = row["caption"] if row else ""
    
    await update.message.reply_text(f"✅ Downloaded! Generating AI metadata and uploading to YouTube...")
    
    # Upload in thread pool
    youtube_id = await asyncio.to_thread(upload_short, shortcode, local_path, creator, caption)
    
    if youtube_id:
        await update.message.reply_text(f"🎉 Success! Uploaded to YouTube Shorts: https://youtu.be/{youtube_id}")
    else:
        await update.message.reply_text("❌ Upload failed. Please check `/logs` for details.")
