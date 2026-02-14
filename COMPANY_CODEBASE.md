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
│   ├── auto_summary/            # AI-powered paper summarization
│   │   └── summary_generation.py
│   │
│   └── paper_parse/
│       ├── paper_parser.py
│       ├── topic_tagger.py
│       ├── arxiv_fetcher.py
│       └── acm_fetcher.py
│
└── web_interface/               # Web server module
    ├── web_server.py            # Local development server
    ├── requirements.txt
    ├── vercel.json              # Vercel deployment config
    │
    ├── api/
    │   └── index.py             # Vercel serverless function
    │
    ├── templates/
    │   └── papers.html
    │
    └── static/
        └── js/
            └── papers.js
```

---

## What NOT to Commit

| File/Directory | Reason |
|----------------|--------|
| `github/` | GitHub sync/deployment (personal use) |
| `paper_collection/token.json` | OAuth tokens (sensitive) |
| `paper_collection/credentials.json` | OAuth credentials (sensitive) |
| `paper_collection/.last_update_run` | Local runtime state |
| `config.yaml` | Personal config with secrets (commit `.example` only) |
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
config.yaml

# Runtime files
.last_update_run

# Personal deployment
github/
*.plist
```

---

## For Users of the Company Codebase

After cloning, users need to:

1. **Set up Gmail API credentials** (see README.md)
2. **Copy config template**: `cp config.yaml.example config.yaml`
3. **Edit config.yaml** with their settings:
   - Database URL (Neon PostgreSQL)
   - Gemini API key (for auto-summary)
   - Email settings
4. **Authenticate**: `python3 paper_collection/daily_update.py --dry-run`
5. **Collect papers**: `./paper_collection/run_update.sh`
6. **Run local server**: `python3 web_interface/web_server.py`

---

## Checklist Before Committing

- [ ] Removed `github/` directory
- [ ] Removed `token.json` and `credentials.json`
- [ ] Removed `config.yaml` (kept `config.yaml.example`)
- [ ] Removed `__pycache__/` directories
- [ ] Removed `.last_update_run`
- [ ] Removed any `.plist` files
- [ ] Created `.gitignore` with company rules
- [ ] README.md has no personal paths/URLs
