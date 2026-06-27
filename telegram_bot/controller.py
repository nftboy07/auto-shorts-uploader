from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from config import secrets
from utils import app_logger, error_logger
from .commands import (
    start_cmd,
    status_cmd,
    health_cmd,
    logs_cmd,
    lastupload_cmd,
    queue_cmd,
    accounts_cmd,
    add_account_cmd,
    remove_account_cmd,
    upload_now_cmd,
    pause_cmd,
    resume_cmd,
    proxies_cmd,
    add_proxy_cmd,
    remove_proxy_cmd,
    stats_cmd,
    history_cmd,
    update_cmd,
    shell_cmd,
    system_info_cmd,
    upload_link_handler,
    login_ig_cmd,
    two_factor_cmd
)

# Global bot application instance
_bot_app = None

def setup_bot() -> ApplicationBuilder:
    """Configures the Telegram Application with all command handlers."""
    token = secrets.TELEGRAM_BOT_TOKEN
    if not token:
        error_logger.critical("TELEGRAM_BOT_TOKEN is missing! Bot cannot start.")
        return None
        
    app = ApplicationBuilder().token(token).build()
    
    # Register core commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", start_cmd))
    app.add_handler(CommandHandler("list", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("health", health_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    app.add_handler(CommandHandler("lastupload", lastupload_cmd))
    app.add_handler(CommandHandler("queue", queue_cmd))
    app.add_handler(CommandHandler("accounts", accounts_cmd))
    app.add_handler(CommandHandler("add_account", add_account_cmd))
    app.add_handler(CommandHandler("remove_account", remove_account_cmd))
    app.add_handler(CommandHandler("upload_now", upload_now_cmd))
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("proxies", proxies_cmd))
    app.add_handler(CommandHandler("add_proxy", add_proxy_cmd))
    app.add_handler(CommandHandler("remove_proxy", remove_proxy_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("update", update_cmd))
    app.add_handler(CommandHandler("restart", update_cmd))  # Alias `/restart` to `/update` restart flow
    
    
    # Direct Reel link sharing handlers
    app.add_handler(CommandHandler("upload_url", upload_link_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), upload_link_handler))
    
    # Admin restricted commands
    app.add_handler(CommandHandler("shell", shell_cmd))
    app.add_handler(CommandHandler("system_info", system_info_cmd))
    
    # Instagram interactive login
    app.add_handler(CommandHandler("login_ig", login_ig_cmd))
    app.add_handler(CommandHandler("2fa", two_factor_cmd))
    
    app_logger.info("Telegram Bot handlers registered successfully.")
    return app

async def run_bot_async() -> None:
    """Runs the Telegram Bot asynchronously."""
    global _bot_app
    _bot_app = setup_bot()
    if not _bot_app:
        return
        
    app_logger.info("Starting Telegram Bot long-polling...")
    await _bot_app.initialize()
    await _bot_app.start()
    await _bot_app.updater.start_polling()
    
def get_bot_app():
    """Retrieves current active bot application instance."""
    return _bot_app
