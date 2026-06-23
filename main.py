import asyncio
import sys
from pathlib import Path

# Add project root to path for imports
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from utils import app_logger, error_logger
from config.secrets import validate_secrets
from database import log_action
from services import start_watchdog
from scheduler import start_scheduler
from telegram_bot import run_bot_async

async def main():
    """Main execution thread for the bot."""
    app_logger.info("Starting Automated Instagram -> YouTube Shorts Agent...")
    
    # 1. Start Watchdog (hooks uncaught exceptions)
    start_watchdog()
    
    # 2. Validate environment secrets
    if not validate_secrets():
        app_logger.warning("Bot is starting, but some required credentials are missing. Check your .env file.")
        
    # 3. Start APScheduler (IG watching & scheduled uploads)
    start_scheduler()
    
    # 4. Start Telegram Command Center Bot (async poll loop)
    await run_bot_async()
    
    log_action("startup", "Bot process started successfully.")
    
    # 5. Keep the event loop running
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        app_logger.info("Bot execution stopped by user request.")
    except Exception as e:
        error_logger.critical(f"Bot crashed on startup: {e}", exc_info=True)
        sys.exit(1)
