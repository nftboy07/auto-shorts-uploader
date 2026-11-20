# Finding: Unprivileged admin takeover (TOFU) → full RCE via Telegram bot

**Program:** nftboy07/auto-shorts-uploader
**Severity:** High (pre-auth privilege escalation to remote code execution, conditioned on an empty admin list — the shipped default)
**Component:** `telegram_bot/commands.py` → `admin_only()`; reachable sink `shell_cmd()`
**Config:** `config/settings.yaml:20` ships `telegram.allowed_admins: []`

## Summary
Every Telegram command is guarded by a single decorator, `admin_only`. When the
configured admin allowlist is empty, `admin_only` **auto-registers the first
caller as administrator** and runs their command. The checked-in default config
ships the allowlist empty, so a freshly deployed bot is in this state. Because a
Telegram bot is reachable by anyone who knows its @username, an unprivileged
attacker who messages the bot before the owner registers wins the gate, becomes
admin, and can then call `/shell <cmd>`, which runs `subprocess.run(cmd, shell=True)`
— arbitrary command execution on the host (and access to the Instagram / YouTube
/ proxy credentials the bot holds).

## Root cause
`telegram_bot/commands.py`:

```python
def admin_only(func):
    async def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        settings = load_settings()
        allowed = settings.get("telegram", {}).get("allowed_admins", [])
        # Auto-register first user as admin if empty
        if not allowed:
            allowed.append(user_id)
            ...
            save_settings(settings)
            await update.message.reply_text(f"... auto-registered as Admin (ID: {user_id}).")
            return await func(update, context, *args, **kwargs)   # <-- runs the command too
        if user_id not in allowed:
            ...  # reject
        return await func(update, context, *args, **kwargs)
```

This is trust-on-first-use (TOFU) with no out-of-band proof of ownership: the
"first caller" is assumed to be the legitimate operator, but nothing prevents an
attacker from being that caller. Note the catch-all `MessageHandler(filters.TEXT
& ~filters.COMMAND, upload_link_handler)` in `controller.py` is also `@admin_only`,
so even a plain text message ("hi") triggers auto-registration — the attacker
does not need to know any command name to seize admin.

The sink, `shell_cmd`:
```python
cmd_str = " ".join(context.args)
res = subprocess.run(cmd_str, shell=True, capture_output=True, text=True, timeout=30)
```
Full, unsanitized shell execution. `/update` (`git pull` + restart) and the IG
login/cookie handlers are likewise reachable once admin.

## Impact for an unprivileged attacker
An attacker with an ordinary Telegram account and no prior authorization gains:
- Administrator control of the bot, then
- Arbitrary code execution on the VPS/container running the bot (uid shown in PoC),
- Theft of Instagram session/cookies, YouTube OAuth tokens, proxy credentials,
  and the Telegram bot token stored on the host.

## Precondition (honest scoping)
The gate only auto-registers when `allowed_admins` is empty. That is the shipped
default and the state of every fresh deploy, re-clone, or `config` reset; the
README (line 116) even documents the behavior. Once a legitimate admin has
registered (list non-empty), this path is closed and the attacker is rejected.
So this is a **race / TOFU window on the empty-list state**, not an unconditional
bypass of a configured allowlist. The window is real because the default ships
empty and the operator must manually win the first message.

## PoC
`poc/exploit_admin_tofu_rce.py` drives the **real** `@admin_only`-wrapped
`shell_cmd` using a throwaway copy of the **real shipped** `config/settings.yaml`
(empty allowlist). An attacker user id never present in any allowlist issues one
`/shell` request and ends up both auto-registered as admin and running an
attacker-chosen command on the host.

```
venv/bin/python poc/exploit_admin_tofu_rce.py
```

Observed output:
```
[*] Shipped settings.yaml allowed_admins = []
[*] Attacker Telegram user id            = 666666666 (@evil_rando)
[*] Attacker is in allowlist beforehand? False
[*] Bot replies: No admin registered. You have been auto-registered as Admin (ID: 666666666).
    Stdout: uid=1000(ubuntu) gid=1000(ubuntu) groups=...,998(docker)
            OWNED_BY_666666666
[+] Attacker now in allowed_admins?  True  (privilege escalation)
[+] Attacker shell command executed? True  (remote code execution)
RESULT: EXPLOIT SUCCEEDED
```
The PoC writes only to a temp dir and does not modify the tracked config.

## Fix
Do not auto-register on an empty allowlist. Require the admin id(s) to be set
explicitly (env var / provisioned config) and reject all callers when the list
is empty, logging the attempt. If a bootstrap flow is desired, gate it on a
one-time secret enrollment token delivered out of band, not on message ordering.
Additionally, remove or hard-restrict `/shell` (no raw `shell=True` on
user-supplied input).

## Submission venue
Owner's private bounty coordination (per task: no Slack post from this session).
Full report + PoC on this PR branch.
