import yaml
from pathlib import Path
from . import secrets

CONFIG_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = CONFIG_DIR / "settings.yaml"

def load_settings() -> dict:
    """Loads the settings.yaml configuration file."""
    if not SETTINGS_FILE.exists():
        return {}
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_settings(settings: dict) -> None:
    """Saves the settings dict to settings.yaml."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(settings, f, default_flow_style=False)
