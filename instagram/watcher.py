import os
import instaloader
from pathlib import Path
from typing import List, Optional

from utils import app_logger, error_logger
from database import get_active_accounts, update_account_checked, video_exists
from config import secrets
from .downloader import download_reel

BASE_DIR = Path(__file__).resolve().parent.parent
SESSION_DIR = BASE_DIR / "config"

class InstagramWatcher:
    def __init__(self):
        self.loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_metadata=False
        )
        self.username = secrets.INSTAGRAM_USERNAME
        self.password = secrets.INSTAGRAM_PASSWORD
        self.is_authenticated = False
        
    def authenticate(self) -> bool:
        """Attempts authentication with Instagram using a session file or username/password."""
        if not self.username or not self.password:
            app_logger.warning("Instagram credentials not configured. Watcher will run in anonymous mode (highly rate-limited).")
            return False
            
        session_file = SESSION_DIR / f"session_{self.username}"
        
        try:
            # Try loading existing session
            if session_file.exists():
                app_logger.info(f"Loading Instagram session from {session_file}")
                self.loader.load_session_from_file(self.username, filename=str(session_file))
                self.is_authenticated = True
                return True
                
            # Log in and save session
            app_logger.info(f"Logging in to Instagram as {self.username}...")
            self.loader.login(self.username, self.password)
            SESSION_DIR.mkdir(parents=True, exist_ok=True)
            self.loader.save_session_to_file(filename=str(session_file))
            self.is_authenticated = True
            app_logger.info(f"Instagram session saved to {session_file}")
            return True
        except Exception as e:
            error_logger.error(f"Instagram authentication failed: {e}")
            self.is_authenticated = False
            return False

    def check_new_reels(self, max_posts_per_profile: int = 5, proxy: Optional[str] = None) -> List[str]:
        """
        Scans all active accounts from database for new Reels.
        Downloads valid reels and returns a list of downloaded shortcodes.
        """
        # Load credentials if not done yet
        if not self.is_authenticated:
            self.authenticate()
            
        accounts = get_active_accounts()
        if not accounts:
            app_logger.info("No active Instagram accounts to watch.")
            return []
            
        downloaded_shortcodes = []
        
        for account in accounts:
            app_logger.info(f"Scanning Instagram account: @{account}")
            try:
                profile = instaloader.Profile.from_username(self.loader.context, account)
                
                # Fetch recent posts
                count = 0
                for post in profile.get_posts():
                    if count >= max_posts_per_profile:
                        break
                        
                    # We are only interested in video posts (Reels/Videos)
                    if post.is_video:
                        shortcode = post.shortcode
                        
                        # Only download if we don't already have it
                        if not video_exists(shortcode):
                            app_logger.info(f"New video found on @{account}: shortcode {shortcode}")
                            local_path = download_reel(shortcode, proxy=proxy)
                            if local_path:
                                downloaded_shortcodes.append(shortcode)
                        count += 1
                        
                update_account_checked(account)
                
            except Exception as e:
                error_logger.error(f"Error checking profile @{account}: {e}")
                
        return downloaded_shortcodes
