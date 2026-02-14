#!/usr/bin/env python3
"""
Fast parallel embedding regeneration using OpenAI batch API.

This script uses OpenAI's batch embedding endpoint which can process
multiple texts in a single API call, making it ~10x faster than sequential.

Usage:
    python regenerate_embeddings_parallel.py
"""

import json
import sys
import time
import urllib.request
from concurrent.futures import as_completed, ThreadPoolExecutor
from pathlib import Path

import psycopg2
import yaml
from psycopg2.extras import RealDictCursor


def load_config():
    """Load configuration from config.yaml."""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def generate_batch_embeddings(texts: list[str], api_key: str) -> list[list[float]]:
    """Generate embeddings for multiple texts in a single API call."""
    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Truncate texts to avoid token limits
    truncated_texts = [t[:8000] for t in texts]

    data = json.dumps(
        {"input": truncated_texts, "model": "text-embedding-3-small", "dimensions": 512}
    ).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
                # Sort by index to maintain order
                embeddings = sorted(result["data"], key=lambda x: x["index"])
                return [e["embedding"] for e in embeddings]
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Retry {attempt + 1}/{max_retries} after error: {e}")
                time.sleep(2**attempt)
            else:
                raise


def process_batch(batch: list[dict], api_key: str, db_url: str) -> int:
    """Process a batch of papers and update the database."""
    if not batch:
        return 0

    # Prepare texts
    texts = []
    for paper in batch:
        title = paper["title"] or ""
        abstract = paper["abstract"] or ""
        authors = paper["authors"] or ""
        texts.append(f"{title} {abstract} {authors}".strip())

    # Generate embeddings
    embeddings = generate_batch_embeddings(texts, api_key)

    # Update database
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    for paper, embedding in zip(batch, embeddings):
        cursor.execute(
            "UPDATE papers SET embedding = %s WHERE id = %s", (embedding, paper["id"])
        )

    conn.commit()
    conn.close()

    return len(batch)


def main():
    print("=" * 60)
    print("OpenAI Parallel Embedding Script (Batch API)")
    print("=" * 60)

    # Load config
    config = load_config()
    api_key = config.get("openai", {}).get("api_key")
    db_url = config.get("database", {}).get("url")

    if not api_key:
        print("ERROR: OpenAI API key not found in config.yaml")
        sys.exit(1)

    print(f"OpenAI API key: {api_key[:20]}...{api_key[-10:]}")

    # Connect to database
    print("\nConnecting to database...")
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get papers without embeddings
    cursor.execute(
        "SELECT id, title, abstract, authors FROM papers WHERE embedding IS NULL ORDER BY id"
    )
    papers = cursor.fetchall()
    conn.close()

    total = len(papers)
    print(f"Papers to process: {total}")

    if total == 0:
        print("✅ All papers already have embeddings!")
        return

    # Process in batches of 100 (OpenAI allows up to 2048)
    BATCH_SIZE = 100
    batches = [papers[i : i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]

    print(f"Processing {len(batches)} batches of up to {BATCH_SIZE} papers each...")
    print()

    start_time = time.time()
    processed = 0
    errors = 0

    # Process batches with thread pool for parallel HTTP requests
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(process_batch, batch, api_key, db_url): i
            for i, batch in enumerate(batches)
        }

        for future in as_completed(futures):
            batch_idx = futures[future]
            try:
                count = future.result()
                processed += count
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (total - processed) / rate if rate > 0 else 0
                print(
                    f"Batch {batch_idx + 1}/{len(batches)}: +{count} papers | "
                    f"Total: {processed}/{total} ({processed / total * 100:.1f}%) | "
                    f"ETA: {eta:.0f}s"
                )
            except Exception as e:
                errors += 1
                print(f"Batch {batch_idx + 1}/{len(batches)}: ERROR - {e}")

    # Final stats
    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print("COMPLETE!")
    print("=" * 60)
    print(f"Processed: {processed}/{total}")
    print(f"Errors: {errors}")
    print(f"Time: {elapsed:.1f} seconds ({elapsed / 60:.1f} minutes)")
    print(f"Rate: {processed / elapsed:.1f} papers/second")

    # Verify
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT COUNT(*) as count FROM papers WHERE embedding IS NOT NULL")
    result = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) as total FROM papers")
    total_papers = cursor.fetchone()
    conn.close()

    print(f"\nFinal: {result['count']}/{total_papers['total']} papers have embeddings")
    print("✅ Done!")


if __name__ == "__main__":
    main()
