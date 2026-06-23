import os
import sys
import time
import psutil
import socket
import threading
import requests
from pathlib import Path
from typing import Optional

from utils import app_logger, error_logger
from config import secrets, load_settings

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_LIMIT_MB = 500.0  # Max memory usage before self-restart to prevent leak
CHECK_INTERVAL_SECONDS = 60

def send_telegram_alert(message: str) -> None:
    """Sends a direct emergency alert to all registered Telegram admins."""
    token = secrets.TELEGRAM_BOT_TOKEN
    if not token:
        return
        
    settings = load_settings()
    admins = settings.get("telegram", {}).get("allowed_admins", [])
    
    for admin_id in admins:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": admin_id, 
            "text": f"⚠️ **[Watchdog Alert]**\n\n{message}",
            "parse_mode": "Markdown"
        }
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            error_logger.error(f"Watchdog failed to send telegram alert to {admin_id}: {e}")

def restart_process() -> None:
    """Restarts the current Python process."""
    app_logger.warning("Initiating self-restart...")
    time.sleep(2)
    os.execv(sys.executable, [sys.executable] + sys.argv)

def check_internet() -> bool:
    """Checks for active internet connectivity by contacting public DNS servers."""
    hosts = [("8.8.8.8", 53), ("1.1.1.1", 53)]
    for host, port in hosts:
        try:
            socket.setdefaulttimeout(3.0)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host, port))
            s.close()
            return True
        except socket.error:
            continue
    return False

def watchdog_loop() -> None:
    """Periodically verifies resources and internet connection."""
    app_logger.info("Watchdog monitor thread started.")
    process = psutil.Process(os.getpid())
    internet_was_down = False
    
    while True:
        try:
            # 1. Check memory leaks
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / (1024 * 1024)
            if mem_mb > MEMORY_LIMIT_MB:
                msg = f"Memory threshold exceeded: {mem_mb:.1f}MB > {MEMORY_LIMIT_MB}MB. Restarting bot."
                error_logger.critical(msg)
                send_telegram_alert(msg)
                restart_process()
                
            # 2. Check internet connection
            if not check_internet():
                if not internet_was_down:
                    msg = "Internet connectivity lost. Monitored tasks may fail."
                    error_logger.warning(msg)
                    # We don't restart immediately on outage, just log and track state
                    internet_was_down = True
            else:
                if internet_was_down:
                    msg = "Internet connectivity restored."
                    app_logger.info(msg)
                    send_telegram_alert(msg)
                    internet_was_down = False
                    
        except Exception as e:
            error_logger.error(f"Error in watchdog check: {e}")
            
        time.sleep(CHECK_INTERVAL_SECONDS)

def start_watchdog() -> None:
    """Hooks unhandled exceptions and starts the watchdog thread."""
    
    # Hook uncaught exceptions to error logs and Telegram alerts
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
            
        msg = f"Unhandled Exception: {exc_value}"
        error_logger.critical(msg, exc_info=(exc_type, exc_value, exc_traceback))
        
        # Send alert
        send_telegram_alert(f"Bot crashed with unhandled exception:\n`{exc_value}`\n\nRestarting automatically.")
        
        # Try to restart
        restart_process()
        
    sys.excepthook = handle_exception
    
    # Start the check thread
    t = threading.Thread(target=watchdog_loop, daemon=True, name="WatchdogMonitor")
    t.start()
