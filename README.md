# Paper Agent

An automated system for collecting academic papers from Google Scholar email alerts, storing them in a searchable database, and browsing them via a web interface.

## Features

- 📧 **Gmail Integration**: Automatically parse Google Scholar alert emails
- 📚 **Paper Database**: PostgreSQL database (via Neon) with title, authors, venue, year, abstract, and links
- 🔍 **Semantic Search**: pgvector-powered similarity search using OpenAI embeddings
- 🏷️ **Topic Tagging**: Automatic topic classification for papers
- 🌐 **Web Interface**: Browse and search papers with a responsive Flask web app
- ⏰ **Daily Updates**: Automated daily collection with email notifications
- 🤖 **Auto-Summary**: AI-powered paper summarization using Gemini API

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Credentials & Configuration

> ⚠️ **SECURITY WARNING**: Never commit credentials or secrets to version control!
> The following files are in `.gitignore` and should NEVER be committed:
> - `config.yaml` (contains API keys and database URLs)
> - `paper_collection/credentials.json` (Google OAuth credentials)
> - `paper_collection/token.json` (OAuth tokens)

#### Step 2.1: Create Configuration File

```bash
cp config.yaml.example config.yaml
```

#### Step 2.2: Set Up Gmail API Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the Gmail API:
   - Navigate to **APIs & Services** > **Library**
   - Search for "Gmail API" and click **Enable**
4. Create OAuth 2.0 credentials:
   - Go to **APIs & Services** > **Credentials**
   - Click **Create Credentials** > **OAuth client ID**
   - Application type: **Desktop app**
   - Download the JSON file
5. Save the downloaded file as `paper_collection/credentials.json`

#### Step 2.3: Configure Database (PostgreSQL/Neon)

1. Create a free database at [Neon](https://neon.tech/)
2. Copy your connection string from the Neon dashboard
3. Add it to `config.yaml`:

```yaml
database:
  url: "postgresql://user:password@host/dbname?sslmode=require"
```

#### Step 2.4: Configure Gemini API (for Auto-Summary)

1. Get an API key from [wearables-ape.io](https://wearables-ape.io/)
2. Add it to `config.yaml`:

```yaml
gemini:
  api_key: "your-api-key-here"
  api_url: "https://api.wearables-ape.io/conversations/sync"
  model: "gemini-2.0-flash"
```

Or set via environment variable:
```bash
export GEMINI_API_KEY="your-api-key-here"
```

#### Step 2.5: Complete Configuration

Edit `config.yaml` with all your settings:

```yaml
# Your email for notifications
notification_email: "your-email@gmail.com"

# Your website URL (for notification emails)
website_url: "http://localhost:5001"

# Gmail settings
gmail:
  credentials_file: "credentials.json"
  token_file: "token.json"
  search_query: "from:scholaralerts-noreply@google.com"

# Data storage
data:
  data_dir: "web_interface/data"

# Database (PostgreSQL via Neon)
database:
  url: "postgresql://user:password@host/dbname?sslmode=require"

# Gemini API (for auto-summary)
gemini:
  api_key: "your-api-key-here"
  api_url: "https://api.wearables-ape.io/conversations/sync"
  model: "gemini-2.0-flash"
```

### 3. Authenticate with Gmail

Run the collector for the first time to authenticate:

```bash
cd paper_collection
python3 daily_update.py --days 1 --dry-run
```

A browser window will open asking you to authorize the app. After authorization, a `token.json` file will be created storing your credentials.

### 4. Collect Papers

```bash
# Collect papers from the last 7 days
cd paper_collection
python3 daily_update.py --days 7 --no-email

# Or use the paper_collector directly for more control
python3 paper_collector.py -n 50 --after 2024/01/01 --save-db --print
```

### 5. Browse Papers

```bash
cd web_interface
python3 web_server.py
```

Visit: http://localhost:5001

## Project Structure

```
paper_agent/
├── config.yaml.example      # Configuration template
├── requirements.txt         # Python dependencies
├── README.md               # This file
│
├── paper_collection/       # Email parsing and data collection
│   ├── config.py           # Configuration management
│   ├── gmail_client.py     # Gmail API client
│   ├── paper_collector.py  # Main paper collection script
│   ├── daily_update.py     # Automated daily update script
│   ├── run_update.sh       # Shell script for cron jobs
│   ├── credentials.json    # OAuth credentials (you create this)
│   ├── token.json          # OAuth token (auto-generated)
│   │
│   ├── auto_summary/       # AI-powered paper summarization
│   │   └── summary_generation.py
│   │
│   └── paper_parse/        # Paper parsing utilities
│       ├── paper_parser.py # Parse Google Scholar HTML
│       ├── topic_tagger.py # Topic classification
│       ├── arxiv_fetcher.py# ArXiv metadata fetcher
│       └── acm_fetcher.py  # ACM metadata fetcher
│
└── web_interface/          # Web application
    ├── web_server.py       # Flask application (local dev)
    ├── requirements.txt    # Web dependencies
    ├── vercel.json         # Vercel deployment config
    ├── api/
    │   └── index.py        # Vercel serverless function
    ├── templates/
    │   └── papers.html     # HTML template
    └── static/
        └── js/
            └── papers.js   # Frontend JavaScript
```

## Usage

### Command Line Options

#### daily_update.py

```bash
python3 daily_update.py [OPTIONS]

Options:
  --days N          Number of days to look back (default: 1)
  --dry-run         Preview without saving to database
  --no-email        Skip sending notification email
  --check           Only run if not already run today
```

#### paper_collector.py

```bash
python3 paper_collector.py [OPTIONS]

Options:
  -n, --num-emails N    Number of emails to fetch (default: 20)
  --after YYYY/MM/DD    Fetch emails after this date
  --before YYYY/MM/DD   Fetch emails before this date
  -q, --query QUERY     Gmail search query
  --save-db             Save papers to database
  --db-path PATH        Custom database path
  --print               Print parsed papers to console
  --skip-tags           Skip topic tagging
  --debug               Print raw text for debugging
```

### Examples

```bash
# Fetch last 30 days of papers
python3 daily_update.py --days 30 --no-email

# Fetch specific date range
python3 paper_collector.py -n 100 --after 2024/01/01 --before 2024/06/30 --save-db

# Dry run to preview
python3 daily_update.py --days 7 --dry-run

# Fetch from a custom email source
python3 paper_collector.py -q "from:alerts@researchgate.net" --save-db
```

## Setting Up Google Scholar Alerts

1. Go to [Google Scholar](https://scholar.google.com/)
2. Search for topics you're interested in
3. Click **Create alert** (envelope icon)
4. Enter your Gmail address
5. Papers will be sent to your inbox and collected by this tool

## Automated Daily Updates

### Using Shell Script

```bash
# Run manually
./paper_collection/run_update.sh

# With options
./paper_collection/run_update.sh --days 7
./paper_collection/run_update.sh --dry-run
```

### Cron Job Setup

Add to your crontab (`crontab -e`):

```bash
# Paper collection only (daily at 5pm)
0 17 * * * /path/to/paper_agent/paper_collection/run_update.sh >> /tmp/paper-update.log 2>&1
```

**Verify cron job:**
```bash
crontab -l
```

**Check logs:**
```bash
cat /tmp/paper-update.log
```

## Database Schema

The papers are stored in SQLite with the following schema:

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| title | TEXT | Paper title (unique) |
| authors | TEXT | Author names |
| venue | TEXT | Publication venue |
| year | TEXT | Publication year |
| abstract | TEXT | Paper abstract/snippet |
| link | TEXT | URL to paper |
| recomm_date | TEXT | Date paper was recommended |
| tags | TEXT | Topic tags |
| created_at | TIMESTAMP | When record was created |

## Troubleshooting

### "No module named 'yaml'"
```bash
pip install pyyaml
```

### "Credentials file not found"
Make sure you've downloaded the OAuth credentials from Google Cloud Console and saved them as `paper_collection/credentials.json`.

### "Token has been expired or revoked"
Delete `paper_collection/token.json` and run the script again to re-authenticate.

### "No emails found"
- Check that you have Google Scholar alerts set up
- Verify the search query matches your alert emails
- Try a larger date range with `--days 30`

### Gmail API Quota Errors
The Gmail API has rate limits. If you hit them:
- Wait a few minutes and try again
- Reduce the number of emails fetched with `-n`

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT

## Acknowledgments

- [Google Scholar](https://scholar.google.com/) for the academic paper alerts
- [Neon](https://neon.tech/) for PostgreSQL serverless database
- [pgvector](https://github.com/pgvector/pgvector) for vector similarity search
- [OpenAI](https://openai.com/) for embeddings API
- [Flask](https://flask.palletsprojects.com/) for the web framework
- [Vercel](https://vercel.com/) for deployment
