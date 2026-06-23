# Automated Instagram → YouTube Shorts Agent

An autonomous Python coding agent system designed to run 24/7 on an Ubuntu VPS, monitor Instagram accounts, download vertical reels, filter them (based on length, aspect ratio, resolution, and hashes), generate optimized YouTube metadata using the Gemini API, and upload them to YouTube Shorts. The agent is controlled and managed through a Telegram Bot Command Center.

---

## Folder Structure

```
project/
├── main.py                     # Entry point
├── Dockerfile                  # Container definition
├── docker-compose.yml          # Multi-container config
├── requirements.txt            # Python dependencies
├── shortsbot.service           # systemd unit file
├── config/
│   ├── settings.yaml           # App configuration settings
│   ├── secrets.py              # Secret manager
│   ├── client_secrets.json     # YouTube OAuth secrets (User supplied)
│   └── youtube_credentials.json# Refreshed YouTube OAuth tokens (Auto generated)
├── telegram/
│   ├── controller.py           # Telegram bot initiator
│   └── commands.py             # Command handlers
├── instagram/
│   ├── watcher.py              # Account monitor
│   └── downloader.py           # Reel downloader
├── youtube/
│   ├── uploader.py             # Resumable YouTube uploader
│   └── metadata_generator.py   # Gemini metadata AI generator
├── scheduler/
│   └── jobs.py                 # Cron schedules and randomized queue planning
├── database/
│   ├── db.py                   # SQLite schema initialization
│   └── models.py               # Data layer queries
├── services/
│   ├── health.py               # Diagnostic runner
│   └── watchdog.py             # Process memory leak checker & error recovery
└── utils/
    ├── helpers.py              # ffprobe video inspector & file hashing
    └── logger.py               # App, error, and upload logging handlers
```

---

## Setup & Installation

### 1. Prerequisite API Credentials

Create a `.env` file in the root folder with the following properties:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
INSTAGRAM_USERNAME=your_instagram_username
INSTAGRAM_PASSWORD=your_instagram_password
GEMINI_API_KEY=your_gemini_api_key
```

### 2. YouTube OAuth Secrets

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable the **YouTube Data API v3**.
3. Create an **OAuth 2.0 Client ID** (Desktop Application type).
4. Download the client secrets JSON, rename it to `client_secrets.json`, and place it in the `config/` directory.

### 3. Deploy on VPS via Docker (Recommended)

To run the containerized agent on your VPS:

```bash
# Build and run in background
docker-compose up --build -d

# Check runtime logs
docker-compose logs -f
```

### 4. Deploy via systemd (Native Ubuntu VPS)

To run the agent directly as a Linux systemd service:

```bash
# Clone the repository to /opt
sudo mv instagram-youtube-shorts-agent /opt/instagram-youtube-shorts-agent
cd /opt/instagram-youtube-shorts-agent

# Set up virtual environment and install requirements
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Register systemd unit
sudo cp shortsbot.service /etc/systemd/system/shortsbot.service
sudo systemctl daemon-reload
sudo systemctl enable shortsbot.service
sudo systemctl start shortsbot.service

# View log outputs
journalctl -u shortsbot.service -f
```

### 5. Automated Deployment (CI/CD via GitHub Actions)

To automatically deploy code modifications to your VPS upon pushing to the `main` branch:
1. Go to your GitHub repository **Settings** > **Secrets and variables** > **Actions**.
2. Define the following Repository Secrets:
   - `VPS_SSH_HOST`: The IP address of your VPS.
   - `VPS_SSH_USER`: The SSH user (e.g. `root` or `ubuntu`).
   - `VPS_SSH_KEY`: The private SSH Key used to log into the VPS (e.g. the content of `id_rsa` or similar).
   - `VPS_SSH_PORT`: The SSH port (defaults to `22` if not specified).
3. The repository contains a workflow file at `.github/workflows/deploy.yml` which triggers on push and automates the pull-rebuild-restart cycle on the host VPS.

---

## Telegram Bot Command Reference

Start a conversation with your bot on Telegram and run `/start`. If the `allowed_admins` field in `config/settings.yaml` is empty, **your user ID will automatically register as the administrator**.

### Bot Commands
- `/start` - Greet user & show commands
- `/status` - Bot running state and queue size
- `/health` - Diagnostics report (CPU/RAM/DB)
- `/logs` - Fetch latest 50 lines of logs
- `/lastupload` - Details of the last video uploaded to YouTube
- `/queue` - Displays list of downloaded Reels pending upload
- `/upload_now` - Forces immediate upload of the first video in the queue
- `/pause` - Suspends monitoring and uploading jobs
- `/resume` - Resumes suspended scheduler jobs
- `/accounts` - Lists monitored Instagram profiles
- `/add_account <username>` - Watch a new profile
- `/remove_account <username>` - Stop watching a profile
- `/proxies` - Lists registered proxies
- `/add_proxy <url>` - Register a proxy (e.g. `http://user:pass@ip:port`)
- `/remove_proxy <url>` - Deregister a proxy
- `/stats` - Analytics report showing views, likes, and subscribers
- `/history` - Recent action history log
- `/update` - Performs a `git pull`, updates requirements, and restarts the process

### Admin-Only Commands
- `/shell <command>` - Executes a shell terminal command on the server (VPS)
- `/system_info` - Detailed host system operating specifications
