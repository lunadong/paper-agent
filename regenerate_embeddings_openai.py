#!/usr/bin/env python3
"""
Regenerate all paper embeddings using OpenAI API.

This script replaces sentence-transformers embeddings with OpenAI text-embedding-3-small
embeddings for compatibility with Vercel deployment.

Cost estimate: ~$0.04 for 2,147 papers
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

import psycopg2
import yaml
from psycopg2.extras import RealDictCursor


def load_config():
    """Load configuration from config.yaml."""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def generate_openai_embedding(text: str, api_key: str) -> list:
    """Generate embedding using OpenAI API."""
    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = json.dumps(
        {
            "input": text[:8000],  # Truncate to avoid token limits
            "model": "text-embedding-3-small",
            "dimensions": 512,
        }
    ).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result["data"][0]["embedding"]
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Retry {attempt + 1}/{max_retries} after error: {e}")
                time.sleep(2**attempt)  # Exponential backoff
            else:
                raise


def main():
    print("=" * 60)
    print("OpenAI Embedding Regeneration Script")
    print("=" * 60)

    # Load config
    config = load_config()
    api_key = config.get("openai", {}).get("api_key")
    db_url = config.get("database", {}).get("url")

    if not api_key:
        print("ERROR: OpenAI API key not found in config.yaml")
        sys.exit(1)

    print(f"OpenAI API key: {api_key[:20]}...{api_key[-10:]}")
    print(f"Database: Neon PostgreSQL")
    print()

    # Connect to database
    print("Connecting to database...")
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get all papers
    cursor.execute("SELECT id, title, abstract, authors FROM papers ORDER BY id")
    papers = cursor.fetchall()
    total = len(papers)

    print(f"Found {total} papers to process")
    print()

    # Process papers
    updated = 0
    errors = 0
    start_time = time.time()

    for i, paper in enumerate(papers):
        paper_id = paper["id"]
        title = paper["title"] or ""
        abstract = paper["abstract"] or ""
        authors = paper["authors"] or ""

        # Create text for embedding (same as before)
        text = f"{title} {abstract} {authors}".strip()

        if not text:
            print(f"[{i + 1}/{total}] Paper {paper_id}: No text, skipping")
            continue

        try:
            # Generate embedding
            embedding = generate_openai_embedding(text, api_key)

            # Update database
            cursor.execute(
                "UPDATE papers SET embedding = %s WHERE id = %s", (embedding, paper_id)
            )
            conn.commit()

            updated += 1

            # Progress update every 50 papers
            if (i + 1) % 50 == 0 or i == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (total - i - 1) / rate if rate > 0 else 0
                print(
                    f"[{i + 1}/{total}] {updated} updated, {errors} errors | "
                    f"{rate:.1f} papers/sec | ETA: {eta:.0f}s"
                )

        except Exception as e:
            errors += 1
            print(f"[{i + 1}/{total}] Paper {paper_id}: ERROR - {e}")
            conn.rollback()

        # Rate limiting: ~3 requests per second to stay under OpenAI limits
        time.sleep(0.35)

    # Final stats
    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print("COMPLETE!")
    print("=" * 60)
    print(f"Total papers: {total}")
    print(f"Updated: {updated}")
    print(f"Errors: {errors}")
    print(f"Time: {elapsed:.1f} seconds ({elapsed / 60:.1f} minutes)")
    print()

    # Verify
    cursor.execute("SELECT COUNT(*) as count FROM papers WHERE embedding IS NOT NULL")
    result = cursor.fetchone()
    print(f"Papers with embeddings: {result['count']}/{total}")

    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
