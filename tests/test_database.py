import unittest
import os
import sqlite3
from pathlib import Path

# Override the database file for testing so we don't mess up development database
import database.db
database.db.DB_FILE = Path(__file__).resolve().parent / "test_shortsbot.db"

import database as db

class TestDatabase(unittest.TestCase):
    def setUp(self):
        # Force a fresh schema initialization for testing
        if database.db.DB_FILE.exists():
            os.remove(database.db.DB_FILE)
        db.init_db()

    def tearDown(self):
        if database.db.DB_FILE.exists():
            os.remove(database.db.DB_FILE)

    def test_add_and_list_accounts(self):
        # Test adding accounts
        self.assertTrue(db.add_account("test_user_1"))
        self.assertTrue(db.add_account("test_user_2"))
        
        # Test duplicate (should handle gracefully)
        self.assertTrue(db.add_account("test_user_1"))
        
        # Verify account lists
        accounts = db.list_accounts()
        usernames = [a["username"] for a in accounts]
        self.assertEqual(len(accounts), 2)
        self.assertIn("test_user_1", usernames)
        self.assertIn("test_user_2", usernames)

    def test_remove_account(self):
        db.add_account("test_user_1")
        self.assertTrue(db.remove_account("test_user_1"))
        
        accounts = db.list_accounts()
        self.assertEqual(len(accounts), 0)

    def test_add_video_and_check_exists(self):
        video_id = "C12345"
        self.assertFalse(db.video_exists(video_id))
        
        # Add metadata
        db.add_video(
            video_id=video_id,
            creator="some_creator",
            caption="test caption",
            duration=30.5,
            file_hash="fakehash123",
            local_path="downloads/C12345.mp4"
        )
        
        self.assertTrue(db.video_exists(video_id))
        self.assertTrue(db.file_hash_exists("fakehash123"))

    def test_add_proxy(self):
        proxy = "http://127.0.0.1:8080"
        self.assertTrue(db.add_proxy(proxy))
        
        proxies = db.get_all_proxies()
        self.assertEqual(len(proxies), 1)
        self.assertEqual(proxies[0]["proxy_url"], proxy)
        self.assertEqual(proxies[0]["status"], "active")
