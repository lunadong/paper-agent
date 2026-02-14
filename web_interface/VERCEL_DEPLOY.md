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

**Note:** The production deployment uses OpenAI's `text-embedding-3-small` for search queries instead of sentence-transformers (which is too large for serverless functions). The database already contains embeddings generated with `all-MiniLM-L6-v2`.

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
   # Enter: postgresql://neondb_owner:npg_yBqTsWUe9d2b@ep-restless-frog-af38fztv-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require

   vercel env add OPENAI_API_KEY
   # Enter: your-openai-api-key
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

- ✅ Browse 2,147 papers with pagination
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

For local development, use the original `web_server.py` with sentence-transformers:

```bash
cd web_interface
/usr/bin/python3 web_server.py
```

This uses the local sentence-transformers model instead of OpenAI API.

## Cost Considerations

- **Vercel**: Free tier includes 100GB bandwidth, serverless function invocations
- **Neon PostgreSQL**: Free tier includes 0.5GB storage, 190 compute hours/month
- **OpenAI**: ~$0.00002 per search query (text-embedding-3-small)
