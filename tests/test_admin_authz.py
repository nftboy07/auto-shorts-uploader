import asyncio
import os
import tempfile
import unittest
from pathlib import Path

import config
from telegram_bot import commands


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class FakeUser:
    def __init__(self, uid, username="u"):
        self.id = uid
        self.username = username


class FakeUpdate:
    def __init__(self, uid, username="u"):
        self.effective_user = FakeUser(uid, username)
        self.message = FakeMessage()


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []


class AdminAuthzTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.settings_file = Path(self._tmp.name) / "settings.yaml"
        self._orig = config.SETTINGS_FILE
        config.SETTINGS_FILE = self.settings_file
        os.environ.pop("TELEGRAM_ADMIN_IDS", None)
        os.environ.pop("ENABLE_SHELL_COMMAND", None)

    def tearDown(self):
        config.SETTINGS_FILE = self._orig
        os.environ.pop("TELEGRAM_ADMIN_IDS", None)
        os.environ.pop("ENABLE_SHELL_COMMAND", None)
        self._tmp.cleanup()

    def _write_settings(self, text):
        self.settings_file.write_text(text, encoding="utf-8")

    def _make_guarded(self):
        calls = []

        @commands.admin_only
        async def guarded(update, context):
            calls.append(update.effective_user.id)
            await update.message.reply_text("OK")
        return guarded, calls

    def test_empty_allowlist_rejects_and_does_not_autoregister(self):
        self._write_settings("telegram:\n  allowed_admins: []\n")
        guarded, calls = self._make_guarded()
        update = FakeUpdate(666666666)
        asyncio.run(guarded(update, FakeContext()))

        self.assertEqual(calls, [], "guarded command must NOT run for empty allowlist")
        self.assertTrue(any("Unauthorized" in r for r in update.message.replies))
        # No trust-on-first-use: the attacker must not be written into settings.
        self.assertEqual(
            (config.load_settings().get("telegram", {}) or {}).get("allowed_admins", []),
            [],
        )

    def test_configured_admin_allowed(self):
        self._write_settings("telegram:\n  allowed_admins:\n    - 111\n")
        guarded, calls = self._make_guarded()
        asyncio.run(guarded(FakeUpdate(111), FakeContext()))
        self.assertEqual(calls, [111])

    def test_non_admin_rejected_when_list_set(self):
        self._write_settings("telegram:\n  allowed_admins:\n    - 111\n")
        guarded, calls = self._make_guarded()
        update = FakeUpdate(222)
        asyncio.run(guarded(update, FakeContext()))
        self.assertEqual(calls, [])
        self.assertTrue(any("Unauthorized" in r for r in update.message.replies))

    def test_env_provisioned_admin_allowed(self):
        self._write_settings("telegram:\n  allowed_admins: []\n")
        os.environ["TELEGRAM_ADMIN_IDS"] = "333, 444"
        guarded, calls = self._make_guarded()
        asyncio.run(guarded(FakeUpdate(444), FakeContext()))
        self.assertEqual(calls, [444])

    def test_shell_disabled_by_default_even_for_admin(self):
        self._write_settings("telegram:\n  allowed_admins:\n    - 111\n")
        marker = Path(self._tmp.name) / "should_not_exist.txt"
        update = FakeUpdate(111)
        ctx = FakeContext([f"echo pwned > {marker}"])
        asyncio.run(commands.shell_cmd(update, ctx))
        self.assertFalse(marker.exists(), "shell must not execute while disabled")
        self.assertTrue(any("disabled" in r.lower() for r in update.message.replies))

    def test_shell_runs_only_when_explicitly_enabled(self):
        self._write_settings("telegram:\n  allowed_admins:\n    - 111\n")
        os.environ["ENABLE_SHELL_COMMAND"] = "1"
        marker = Path(self._tmp.name) / "enabled_marker.txt"
        update = FakeUpdate(111)
        ctx = FakeContext([f"echo ok > {marker}"])
        asyncio.run(commands.shell_cmd(update, ctx))
        self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
