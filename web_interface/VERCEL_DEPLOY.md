# Vercel Deployment Guide

This guide explains how to deploy the Paper Browser to Vercel.

## Prerequisites

1. [Vercel account](https://vercel.com/signup)
2. [Vercel CLI](https://vercel.com/docs/cli) (optional but recommended)
3. OpenAI API key for semantic search

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Vercel CDN    │────▶│ Serverless Flask │────▶│ Neon PostgreSQL │
│  (static files) │     │   (api/index.py) │     │   (pgvector)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │   OpenAI API     │
                        │ (text-embedding) │
                        └──────────────────┘
```

**Note:** Both local development and production use OpenAI's `text-embedding-3-small` (512 dimensions) for embeddings and search queries. The database stores pre-computed embeddings using pgvector.

## Deployment Steps

### Option 1: Deploy via Vercel CLI

1. Install Vercel CLI:
   ```bash
   npm install -g vercel
   ```

2. Navigate to the web_interface directory:
   ```bash
   cd web_interface
   ```

3. Login to Vercel:
   ```bash
   vercel login
   ```

4. Deploy:
   ```bash
   vercel
   ```

5. Set environment variables:
   ```bash
   vercel env add DATABASE_URL
   # Enter your Neon PostgreSQL connection string

   vercel env add OPENAI_API_KEY
   # Enter your OpenAI API key
   ```

6. Redeploy to use the environment variables:
   ```bash
   vercel --prod
   ```

### Option 2: Deploy via GitHub

1. Push the code to a GitHub repository

2. Go to [Vercel Dashboard](https://vercel.com/dashboard)

3. Click "Add New" → "Project"

4. Import your GitHub repository

5. Set the **Root Directory** to `web_interface`

6. Add environment variables:
   - `DATABASE_URL`: Your Neon PostgreSQL connection string
   - `OPENAI_API_KEY`: Your OpenAI API key

7. Click "Deploy"

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | Neon PostgreSQL connection URL | Yes |
| `OPENAI_API_KEY` | OpenAI API key for semantic search | Yes (for AI search) |

## File Structure

```
web_interface/
├── api/
│   ├── index.py          # Serverless Flask app
│   └── requirements.txt  # Python dependencies
├── static/
│   └── js/
│       └── papers.js     # Frontend JavaScript
├── templates/
│   └── papers.html       # HTML template
├── vercel.json           # Vercel configuration
└── VERCEL_DEPLOY.md      # This file
```

## Features

- ✅ Browse papers with pagination
- ✅ Semantic search (AI-powered, uses OpenAI embeddings)
- ✅ Keyword search (SQL ILIKE fallback)
- ✅ Topic filtering
- ✅ Date range filtering
- ✅ Similar papers API
- ✅ Responsive design

## Troubleshooting

### "OpenAI embedding failed, falling back to keyword search"
- Ensure `OPENAI_API_KEY` is set correctly in Vercel environment variables
- Check your OpenAI API quota

### Database connection errors
- Verify `DATABASE_URL` is correct
- Ensure Neon database allows connections from Vercel IPs

### Cold start latency
- First request may take 2-5 seconds due to serverless cold start
- Subsequent requests are fast

## Local Development

For local development, use `web_server.py`:

```bash
cd web_interface
python3 web_server.py
```

This connects to the same Neon PostgreSQL database and uses OpenAI API for embeddings, just like production.

## Cost Considerations

- **Vercel**: Free tier includes 100GB bandwidth, serverless function invocations
- **Neon PostgreSQL**: Free tier includes 0.5GB storage, 190 compute hours/month
- **OpenAI**: ~$0.00002 per search query (text-embedding-3-small)
