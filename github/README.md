# GitHub Sync Guide

Utilities to push paper data to GitHub.

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

---

## Troubleshooting

### Push fails with "Permission denied"
```bash
# Check SSH key is added to GitHub
ssh -T git@github.com

# Or use HTTPS with token
git remote set-url origin https://YOUR_TOKEN@github.com/YOUR_USERNAME/paper_agent.git
```

### Cron not running
```bash
# Check cron is running
pgrep cron

# Check cron logs (macOS)
log show --predicate 'process == "cron"' --last 1h

# Test script manually
/path/to/paper_agent/github/run_sync.sh --dry-run
```

---

## Architecture

```
┌─────────────────┐     ┌─────────────┐     ┌─────────────┐
│  Gmail (Scholar │────▶│   Neon      │────▶│   GitHub    │
│     Alerts)     │     │  PostgreSQL │     │    Repo     │
└─────────────────┘     └─────────────┘     └──────┬──────┘
                                                   │
                             ┌─────────────────────┘
                             ▼
                       ┌───────────┐
                       │  Vercel   │
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
3. Papers saved to Neon PostgreSQL database
4. `github_push.py` pushes code changes to GitHub
5. Vercel auto-deploys on push
6. Users see updated papers on the web
