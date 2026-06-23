import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

def load_env(env_path: Path = BASE_DIR / ".env"):
    """Simple parser to load environment variables from a .env file."""
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

# Load environment variables from .env if present
load_env()

# API Keys and Secrets
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# YouTube credentials
YOUTUBE_CLIENT_SECRETS_FILE = os.getenv(
    "YOUTUBE_CLIENT_SECRETS_FILE", 
    str(BASE_DIR / "config" / "client_secrets.json")
)
YOUTUBE_CREDENTIALS_FILE = os.getenv(
    "YOUTUBE_CREDENTIALS_FILE", 
    str(BASE_DIR / "config" / "youtube_credentials.json")
)

def validate_secrets() -> bool:
    """Validate that required secrets are present."""
    required = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print(f"Warning: Missing required secrets: {', '.join(missing)}")
        return False
    return True
