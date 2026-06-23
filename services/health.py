import os
import psutil
from pathlib import Path
from typing import Dict, Any

from utils import app_logger, error_logger
from config import secrets, load_settings
from database import get_connection

BASE_DIR = Path(__file__).resolve().parent.parent

def check_system_resources() -> Dict[str, Any]:
    """Inspects CPU, RAM, and Disk metrics."""
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    return {
        "cpu_usage_pct": cpu,
        "ram_usage_pct": ram.percent,
        "ram_available_mb": ram.available / (1024 * 1024),
        "disk_usage_pct": disk.percent,
        "disk_free_gb": disk.free / (1024 * 1024 * 1024)
    }

def check_database() -> bool:
    """Verifies SQLite connection integrity."""
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except Exception as e:
        error_logger.error(f"Health check: Database is unreachable: {e}")
        return False

def check_file_systems() -> Dict[str, bool]:
    """Ensures directories exist and are writeable."""
    paths = {
        "logs": BASE_DIR / "logs",
        "downloads": BASE_DIR / "downloads",
        "uploads": BASE_DIR / "uploads"
    }
    
    status = {}
    for name, path in paths.items():
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception:
                status[name] = False
                continue
                
        # Test write permission
        test_file = path / ".health_test"
        try:
            test_file.touch()
            test_file.unlink()
            status[name] = True
        except Exception:
            status[name] = False
            
    return status

def run_diagnostics() -> Dict[str, Any]:
    """Runs a full diagnostics suite."""
    resources = check_system_resources()
    db_ok = check_database()
    fs_status = check_file_systems()
    
    # Check secrets configuration
    credentials_configured = {
        "telegram_token_present": bool(secrets.TELEGRAM_BOT_TOKEN),
        "instagram_user_present": bool(secrets.INSTAGRAM_USERNAME),
        "gemini_api_key_present": bool(secrets.GEMINI_API_KEY),
        "youtube_client_secrets_present": Path(secrets.YOUTUBE_CLIENT_SECRETS_FILE).exists(),
        "youtube_credentials_present": Path(secrets.YOUTUBE_CREDENTIALS_FILE).exists()
    }
    
    overall_health = db_ok and all(fs_status.values()) and resources["disk_usage_pct"] < 95.0
    
    return {
        "status": "healthy" if overall_health else "unhealthy",
        "database_connected": db_ok,
        "file_system_writeable": fs_status,
        "system_resources": resources,
        "credentials": credentials_configured
    }
