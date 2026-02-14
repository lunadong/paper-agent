# Company Codebase Guide

This guide explains what to commit when sharing Paper Agent to a company-wide codebase, allowing others to set up their own local paper collection server.

## What to Commit

### Core Files

```
paper_agent/
├── README.md                    # Main documentation
├── config.yaml.example          # Config template (NOT config.yaml)
├── requirements.txt             # Python dependencies
│
├── paper_collection/            # Paper collection module
│   ├── config.py
│   ├── gmail_client.py
│   ├── paper_collector.py
│   ├── daily_update.py
│   ├── run_update.sh
│   │
│   └── paper_parse/
│       ├── paper_parser.py
│       ├── paper_db.py
│       ├── index_builder.py
│       ├── topic_tagger.py
│       ├── arxiv_fetcher.py
│       └── acm_fetcher.py
│
└── web_interface/               # Web server module
    ├── web_server.py
    ├── requirements.txt
    │
    ├── templates/
    │   └── papers.html
    │
    └── static/
        └── js/
            └── papers.js
```

### Optional: Empty Data Directory

Create placeholder so directory structure is preserved:

```bash
mkdir -p web_interface/data
touch web_interface/data/.gitkeep
```

---

## What NOT to Commit

| File/Directory | Reason |
|----------------|--------|
| `github/` | GitHub sync/deployment (personal use) |
| `paper_collection/token.json` | OAuth tokens (sensitive) |
| `paper_collection/credentials.json` | OAuth credentials (sensitive) |
| `paper_collection/.last_update_run` | Local runtime state |
| `config.yaml` | Personal config (commit `.example` only) |
| `web_interface/data/papers.db` | Personal paper database |
| `web_interface/data/papers.index` | Personal FAISS index |
| `web_interface/data/paper_ids.json` | Personal paper IDs |
| `__pycache__/` | Python cache |
| `*.log` | Log files |
| `*.plist` | Personal cron configs |

---

## Company .gitignore

Use this `.gitignore` for the company codebase:

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.env
.venv
venv/
ENV/

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Logs
*.log

# Secrets (NEVER commit)
token.json
credentials.json

# Personal data
web_interface/data/*.db
web_interface/data/*.index
web_interface/data/*.json
!web_interface/data/.gitkeep

# Personal configuration
config.yaml
config.yml

# Runtime files
.last_update_run

# Personal deployment
github/
*.plist
```

---

## Copying to Company Repo

### Option 1: Manual Copy

```bash
# Create company repo directory
mkdir paper_agent_company
cd paper_agent_company

# Copy core files
cp -r /path/to/paper_agent/paper_collection .
cp -r /path/to/paper_agent/web_interface .
cp /path/to/paper_agent/README.md .
cp /path/to/paper_agent/config.yaml.example .
cp /path/to/paper_agent/requirements.txt .

# Remove sensitive/personal files
rm -f paper_collection/token.json
rm -f paper_collection/credentials.json
rm -f paper_collection/.last_update_run
rm -rf paper_collection/__pycache__
rm -rf paper_collection/paper_parse/__pycache__
rm -f web_interface/data/*.db
rm -f web_interface/data/*.index
rm -f web_interface/data/*.json

# Create .gitkeep for empty data dir
mkdir -p web_interface/data
touch web_interface/data/.gitkeep

# Create .gitignore (paste content from above)
```

### Option 2: Git Archive (Excludes .gitignore'd files)

```bash
cd /path/to/paper_agent
git archive --format=tar HEAD | tar -x -C /path/to/company_repo/
```

---

## For Users of the Company Codebase

After cloning, users need to:

1. **Set up Gmail API credentials** (see README.md)
2. **Copy config template**: `cp config.yaml.example config.yaml`
3. **Edit config.yaml** with their email settings
4. **Authenticate**: `python3 paper_collection/daily_update.py --dry-run`
5. **Collect papers**: `./paper_collection/run_update.sh`
6. **Run local server**: `python3 web_interface/web_server.py`

---

## Checklist Before Committing

- [ ] Removed `github/` directory
- [ ] Removed `token.json` and `credentials.json`
- [ ] Removed `config.yaml` (kept `config.yaml.example`)
- [ ] Removed personal data from `web_interface/data/`
- [ ] Removed `__pycache__/` directories
- [ ] Removed `.last_update_run`
- [ ] Removed any `.plist` files
- [ ] Created `.gitignore` with company rules
- [ ] README.md has no personal paths/URLs
