import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Format for loggers
LOG_FORMAT = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s", 
    datefmt="%Y-%m-%d %H:%M:%S"
)

def setup_logger(name: str, log_file: str, level=logging.INFO) -> logging.Logger:
    """Configures and returns a logger that outputs to console and a file."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers if already configured
    if logger.handlers:
        return logger

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(LOG_FORMAT)
    logger.addHandler(console_handler)

    # File Handler
    file_path = LOGS_DIR / log_file
    file_handler = RotatingFileHandler(
        str(file_path), 
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(LOG_FORMAT)
    logger.addHandler(file_handler)

    return logger

# Loggers for specific modules
app_logger = setup_logger("app", "app.log")
error_logger = setup_logger("error", "error.log", level=logging.ERROR)
upload_logger = setup_logger("upload", "upload.log")

# Add app.log handler to error_logger so errors also show in app.log
for handler in app_logger.handlers:
    if isinstance(handler, logging.FileHandler) or isinstance(handler, RotatingFileHandler):
        error_logger.addHandler(handler)



def get_latest_logs(log_name: str = "app.log", lines_count: int = 100) -> str:
    """Returns the last N lines of a specific log file."""
    log_path = LOGS_DIR / log_name
    if not log_path.exists():
        return f"Log file {log_name} not found."
    
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            last_lines = lines[-lines_count:]
            return "".join(last_lines)
    except Exception as e:
        return f"Error reading log file: {e}"
