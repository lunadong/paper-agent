# GitHub Sync & Deployment Guide

Utilities to push paper data to GitHub and deploy via cloud services.

## Files

| File | Description |
|------|-------------|
| `github_push.py` | Python script to push data to GitHub |
| `run_sync.sh` | Shell script: collects papers + pushes to GitHub |
| `com.paper-agent.github-sync.plist` | macOS launchd template (alternative to cron) |

## Quick Start

### 1. Set Up GitHub Repository

```bash
# Initialize git (if not already done)
cd /path/to/paper_agent
git init

# Create .gitignore
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
*.pyo
.DS_Store
token.json
credentials.json
*.log
.last_update_run
EOF

# Add and commit
git add .
git commit -m "Initial commit"

# Create repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/paper_agent.git
git branch -M main
git push -u origin main
```

### 2. Test the Sync

```bash
# Dry run first
./run_sync.sh --dry-run

# Real run
./run_sync.sh
```

### 3. Set Up Automated Sync (Cron)

```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 5pm)
0 17 * * * /path/to/paper_agent/github/run_sync.sh >> /tmp/paper-sync.log 2>&1
```

---

## Usage Reference

### Manual Push

```bash
# Push if there are changes
python3 github_push.py

# Preview without pushing
python3 github_push.py --dry-run

# Force push even with no changes
python3 github_push.py --force
```

### Combined Script (Collect + Push)

```bash
# Run full sync
./run_sync.sh

# Dry run
./run_sync.sh --dry-run
```

### What Gets Pushed

Only `web_interface/data/` is pushed:
- `papers.db` - SQLite database
- `papers.index` - FAISS search index
- `paper_ids.json` - Paper ID mappings

Code changes should be committed manually/separately.

---

## Deployment Options

### Option A: Render (Recommended)

[Render](https://render.com) offers free tier hosting with automatic deploys from GitHub.

#### Step 1: Prepare Repository

Ensure your GitHub repo has the latest code and data:
```bash
./run_sync.sh
```

#### Step 2: Create Render Account

1. Go to [render.com](https://render.com)
2. Sign up with your GitHub account

#### Step 3: Create Web Service

1. Click **New** > **Web Service**
2. Connect your GitHub repository
3. Configure settings:

| Setting | Value |
|---------|-------|
| **Name** | `paper-agent` (or your choice) |
| **Region** | Choose closest to you |
| **Branch** | `main` |
| **Root Directory** | `web_interface` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn web_server:app` |

4. Select **Free** plan
5. Click **Create Web Service**

#### Step 4: Access Your Site

After deployment (2-3 minutes), your site will be at:
```
https://paper-agent.onrender.com
```

#### Step 5: Enable Auto-Deploy

Render auto-deploys on every push to `main`. Your cron job pushes data daily, so:
- Cron runs at 5pm → pushes new papers to GitHub
- GitHub push → triggers Render redeploy
- Site updated automatically!

---

### Option B: Railway

[Railway](https://railway.app) offers simple deployment with generous free tier.

#### Setup

1. Go to [railway.app](https://railway.app)
2. Click **New Project** > **Deploy from GitHub repo**
3. Select your repository
4. Configure:
   - **Root Directory**: `web_interface`
   - **Start Command**: `gunicorn web_server:app`

---

### Option C: Fly.io

[Fly.io](https://fly.io) offers global deployment with free tier.

#### Setup

1. Install flyctl:
   ```bash
   brew install flyctl
   ```

2. Login and launch:
   ```bash
   cd web_interface
   fly launch
   ```

3. Create `fly.toml`:
   ```toml
   app = "paper-agent"
   primary_region = "sjc"

   [build]
     builder = "paketobuildpacks/builder:base"

   [env]
     PORT = "8080"

   [http_service]
     internal_port = 8080
     force_https = true

   [[services]]
     internal_port = 8080
     protocol = "tcp"

     [[services.ports]]
       port = 80
       handlers = ["http"]

     [[services.ports]]
       port = 443
       handlers = ["tls", "http"]
   ```

4. Deploy:
   ```bash
   fly deploy
   ```

---

### Option D: Self-Hosted (VPS)

For full control, deploy on a VPS (DigitalOcean, Linode, etc.).

#### Setup on Ubuntu

```bash
# Install dependencies
sudo apt update
sudo apt install python3-pip nginx

# Clone repository
git clone https://github.com/YOUR_USERNAME/paper_agent.git
cd paper_agent/web_interface

# Install Python packages
pip3 install -r requirements.txt
pip3 install gunicorn

# Test
gunicorn web_server:app --bind 0.0.0.0:5001
```

#### Configure Nginx

```nginx
# /etc/nginx/sites-available/paper-agent
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/paper-agent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### Configure Systemd Service

```ini
# /etc/systemd/system/paper-agent.service
[Unit]
Description=Paper Agent Web Server
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/paper_agent/web_interface
ExecStart=/usr/local/bin/gunicorn web_server:app --bind 127.0.0.1:5001
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable paper-agent
sudo systemctl start paper-agent
```

---

## Troubleshooting

### Push fails with "Permission denied"
```bash
# Check SSH key is added to GitHub
ssh -T git@github.com

# Or use HTTPS with token
git remote set-url origin https://YOUR_TOKEN@github.com/YOUR_USERNAME/paper_agent.git
```

### Render deploy fails
- Check build logs in Render dashboard
- Ensure `requirements.txt` exists in `web_interface/`
- Verify `gunicorn` is in requirements

### Cron not running
```bash
# Check cron is running
pgrep cron

# Check cron logs (macOS)
log show --predicate 'process == "cron"' --last 1h

# Test script manually
/path/to/paper_agent/github/run_sync.sh --dry-run
```

### Data not updating on deployed site
1. Check cron job is running: `crontab -l`
2. Check push log: `cat /tmp/paper-sync.log`
3. Verify GitHub repo has latest data
4. Check Render/Railway deploy logs

---

## Architecture

```
┌─────────────────┐     ┌─────────────┐     ┌─────────────┐
│  Gmail (Scholar │────▶│   Local     │────▶│   GitHub    │
│     Alerts)     │     │  Database   │     │    Repo     │
└─────────────────┘     └─────────────┘     └──────┬──────┘
                                                    │
                              ┌─────────────────────┘
                              ▼
                        ┌───────────┐
                        │  Render/  │
                        │  Railway  │
                        └─────┬─────┘
                              │
                              ▼
                        ┌───────────┐
                        │   Users   │
                        │  (Web UI) │
                        └───────────┘
```

**Daily Flow:**
1. Cron triggers `run_sync.sh` at 5pm
2. `run_update.sh` fetches new papers from Gmail
3. Papers saved to local SQLite database
4. `github_push.py` pushes `web_interface/data/` to GitHub
5. Cloud platform detects push, redeploys automatically
6. Users see updated papers on the web
