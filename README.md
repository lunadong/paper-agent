# Paper Agent

An automated system for collecting academic papers from Google Scholar email
alerts, storing them in a searchable database, and browsing them via a web
interface with AI-powered summarization.

## Features

- **Gmail Integration**: Automatically parse Google Scholar alert emails
- **Paper Database**: PostgreSQL database (via Neon) with pgvector support
- **Semantic Search**: Vector similarity search using OpenAI embeddings
- **Topic Tagging**: Automatic topic classification (exact + semantic match)
- **Primary Topic**: Identify the main research area for each paper
- **AI Summarization**: Two-stage summarization using Gemini API
  - Stage 1: Topic classification from PDF/abstract
  - Stage 2: Detailed structured summary with evaluation highlights
- **Web Interface**: Browse, search, and view paper summaries
- **Daily Updates**: Automated collection with parallel processing
- **Vercel Deployment**: Ready for serverless deployment

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Credentials & Configuration

> **SECURITY WARNING**: Never commit credentials to version control!
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
2. Enable pgvector extension: `CREATE EXTENSION vector;`
3. Copy your connection string from the Neon dashboard
4. Add it to `config.yaml`:

```yaml
database:
  url: "postgresql://user:password@host/dbname?sslmode=require"
```

#### Step 2.4: Configure OpenAI API (for Semantic Search)

1. Get an API key from [OpenAI](https://platform.openai.com/)
2. Add it to `config.yaml`:

```yaml
openai:
  api_key: "your-openai-api-key"
  embedding_model: "text-embedding-3-small"
```

#### Step 2.5: Configure Gemini API (for AI Summarization)

1. Get an API key from your Gemini API provider
2. Add it to `config.yaml`:

```yaml
gemini:
  api_key: "your-api-key-here"
  api_url: "https://your-api-endpoint/conversations/sync"
  model: "gemini-2.0-flash"
  lightweight_model: "gemini-2.0-flash-lite"  # For topic classification
```

### 3. Authenticate with Gmail

Run the collector for the first time to authenticate:

```bash
cd paper_collection
python3 daily_update.py --days 1 --dry-run
```

A browser window will open asking you to authorize the app.

### 4. Collect Papers

```bash
# Collect papers from the last 7 days
cd paper_collection
python3 daily_update.py --days 7 --no-email

# With parallel summary generation (4 workers)
python3 daily_update.py --days 7 --no-email --workers 4
```

### 5. Generate Summaries

```bash
cd paper_collection/paper_summary

# Generate summary for a specific paper
python3 summary_generation.py --paper-id 123 --save-db

# Process latest 10 papers with 4 parallel workers
python3 summary_generation.py --latest 10 --workers 4 --save-db

# Process all papers without summaries (with checkpointing)
python3 summary_generation.py --all --checkpoint progress.json --save-db
```

### 6. Browse Papers

```bash
cd web_interface
python3 web_server.py
```

Visit: http://localhost:5001

## Project Structure

```
paper-agent/
|-- config.yaml.example      # Configuration template
|-- requirements.txt         # Python dependencies
|-- README.md                # This file
|
|-- paper_collection/        # Email parsing and data collection
|   |-- config.py            # Configuration management
|   |-- gmail_client.py      # Gmail API client
|   |-- paper_collector_wo_LLM.py  # Paper collection (keyword tagging)
|   |-- paper_db.py          # PostgreSQL database with connection pooling
|   |-- daily_update.py      # Automated daily update with parallel processing
|   |-- run_update.sh        # Shell script for cron jobs
|   |
|   |-- paper_summary/       # AI-powered paper summarization
|   |   |-- summary_generation.py  # Two-stage summary generation
|   |   +-- prompts/         # Prompt templates
|   |       |-- prompt.txt           # Main summary prompt
|   |       |-- prompt_topic.txt     # Topic classification prompt
|   |       |-- background_*.txt     # Topic-specific backgrounds
|   |       |-- summary_template.json
|   |       +-- summary_example.json
|   |
|   +-- paper_metadata/      # Paper parsing utilities
|       |-- paper_parser.py  # Parse Google Scholar HTML
|       |-- topic_tagger.py  # Topic classification (exact + semantic)
|       +-- arxiv_fetcher.py # ArXiv metadata fetcher
|
+-- web_interface/           # Web application
    |-- db.py                # Shared database utilities
    |-- index.py             # Vercel serverless entry point
    |-- web_server.py        # Flask application (local dev)
    |-- paper_detail.py      # Paper detail page blueprint
    |-- vercel.json          # Vercel deployment config
    |-- VERCEL_DEPLOY.md     # Vercel deployment guide
    |-- templates/
    |   |-- papers.html      # Main papers list page
    |   +-- paper_detail.html # Paper detail with summary
    +-- static/js/
        +-- papers.js        # Frontend JavaScript
```

## Usage

### daily_update.py

```bash
python3 daily_update.py [OPTIONS]

Options:
  --days N          Number of days to look back (default: 1)
  --dry-run         Preview without saving to database
  --no-email        Skip sending notification email
  --skip-tags       Skip summary generation step
  --workers N       Parallel workers for summary generation (default: 1)
  --check           Only run if not already run today
```

### summary_generation.py

```bash
python3 summary_generation.py [OPTIONS]

Input Options (one required):
  --paper-id ID     Process a specific paper by database ID
  --latest N        Process the latest N papers
  --all             Process ALL papers in the database
  --pdf-url URL     Process a single PDF from URL

Processing Options:
  --workers N       Parallel workers (default: 1)
  --checkpoint FILE Checkpoint file for resumable processing
  --resume          Resume from checkpoint
  --overwrite       Overwrite existing summaries

Output Options:
  --save-db         Save results to database
  --prompt-file F   Save generated prompt to file (for debugging)
  --model MODEL     Override the Gemini model
```

### topic_tagger.py

```bash
python3 topic_tagger.py [OPTIONS]

Options:
  --stats           Show topic statistics
  --retag           Re-tag all papers
  --retag-topic T   Re-tag a specific topic only
```

## Topics

The system supports the following research topics:

| Tag | Full Name | Search Method |
|-----|-----------|---------------|
| RAG | Retrieval-Augmented Generation | Exact match |
| Agent | Agentic AI | Exact + Semantic |
| Memory | Memory Systems | Exact match |
| P13N | Personalization | Semantic |
| Factuality | Factuality, Hallucination | Semantic |
| Reasoning | Reasoning, Planning | Exact match |
| RL | Reinforcement Learning | Exact match |
| Pretraining | LLM Pre-training | Exact + Semantic |
| KG | Knowledge Graph | Exact match |
| QA | Question Answering | Exact match |
| Recommendation | Recommendation Systems | Semantic |
| MM | Multi-Modal | Semantic |
| Speech | Speech Processing | Exact match |
| Benchmark | Evaluation Benchmarks | Exact match |

## Database Schema

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| title | TEXT | Paper title |
| authors | TEXT | Author names |
| venue | TEXT | Publication venue |
| year | TEXT | Publication year |
| abstract | TEXT | Paper abstract |
| link | TEXT | URL to paper |
| recomm_date | TEXT | Date recommended |
| topic | TEXT | All topic tags (comma-separated) |
| primary_topic | TEXT | Main research area |
| embedding | vector(512) | OpenAI embedding |
| summary_basics | JSONB | Basic paper info |
| summary_core | JSONB | Core problem and novelty |
| summary_methods_evidence | JSONB | Methods and evaluation |
| summary_figures | JSONB | Figure descriptions |
| summary_generated_at | TEXT | When summary was generated |
| created_at | TIMESTAMP | Record creation time |

## Troubleshooting

### "No module named 'yaml'"
```bash
pip install pyyaml
```

### "Credentials file not found"
Download OAuth credentials from Google Cloud Console and save as
`paper_collection/credentials.json`.

### "Token has been expired or revoked"
Delete `paper_collection/token.json` and re-authenticate.

### "PDF fetch failed"
- Some papers may not have accessible PDFs
- The system falls back to abstract-only topic classification
- Check `--checkpoint` file for error details

### Semantic Search Not Working
- Verify `OPENAI_API_KEY` is set
- Check embedding coverage:
  `SELECT COUNT(*) FROM papers WHERE embedding IS NOT NULL`

### Summary Generation Errors
- Check Gemini API key and endpoint in config.yaml
- Use `--checkpoint` for resumable batch processing
- Review checkpoint file for error categorization

## Deployment

### Vercel Deployment

See [web_interface/VERCEL_DEPLOY.md](web_interface/VERCEL_DEPLOY.md)
for details.

Quick steps:
1. Install Vercel CLI: `npm install -g vercel`
2. Navigate to web_interface: `cd web_interface`
3. Deploy: `vercel`
4. Set environment variables: `DATABASE_URL`, `OPENAI_API_KEY`
5. Deploy to production: `vercel --prod`

## Stats

- **~9,200 lines of code** across 29 files
- Python (67%), HTML/JS (20%), JSON/Text (13%)

## License

MIT

## Acknowledgments

- [Google Scholar](https://scholar.google.com/) for paper alerts
- [Neon](https://neon.tech/) for PostgreSQL serverless database
- [pgvector](https://github.com/pgvector/pgvector) for vector search
- [OpenAI](https://openai.com/) for embeddings API
- [Google Gemini](https://deepmind.google/technologies/gemini/)
  for summarization
- [Flask](https://flask.palletsprojects.com/) for the web framework
- [Vercel](https://vercel.com/) for deployment
