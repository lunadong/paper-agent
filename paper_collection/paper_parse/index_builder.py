#!/usr/bin/python3
"""
Embedding Generator for Semantic Search

Creates embeddings for all papers and builds a FAISS index.

Usage:
    python build_index.py

This will:
1. Load all papers from the database
2. Generate embeddings using sentence-transformers
3. Build a FAISS index
4. Save the index and paper IDs mapping
"""

import json
import os
import sqlite3

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# Paths (relative to script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "..", "web_interface", "data")
DB_PATH = os.path.join(DATA_DIR, "papers.db")
INDEX_PATH = os.path.join(DATA_DIR, "papers.index")
IDS_PATH = os.path.join(DATA_DIR, "paper_ids.json")

# Model for generating embeddings
MODEL_NAME = "all-MiniLM-L6-v2"  # Fast and good quality, 384 dimensions


def get_all_papers():
    """Load all papers from the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, authors, venue, abstract FROM papers")
    papers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return papers


def create_paper_text(paper):
    """Create a text representation of a paper for embedding."""
    parts = []

    if paper.get("title"):
        parts.append(paper["title"])

    if paper.get("authors"):
        parts.append(f"Authors: {paper['authors']}")

    if paper.get("venue"):
        parts.append(f"Venue: {paper['venue']}")

    if paper.get("abstract"):
        parts.append(paper["abstract"])

    return " ".join(parts)


def build_index():
    """Build FAISS index from all papers."""
    print("Loading papers from database...")
    papers = get_all_papers()
    print(f"Found {len(papers)} papers")

    if not papers:
        print("No papers found. Exiting.")
        return

    print(f"\nLoading model: {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)

    print("\nGenerating embeddings...")
    texts = [create_paper_text(p) for p in papers]
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

    # Normalize embeddings for cosine similarity
    faiss.normalize_L2(embeddings)

    print(f"\nEmbedding shape: {embeddings.shape}")

    # Build FAISS index
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(
        dimension
    )  # Inner product (cosine similarity after normalization)
    index.add(embeddings)

    print(f"Index built with {index.ntotal} vectors")

    # Save index
    print(f"\nSaving index to {INDEX_PATH}...")
    faiss.write_index(index, INDEX_PATH)

    # Save paper IDs mapping
    paper_ids = [p["id"] for p in papers]
    print(f"Saving paper IDs to {IDS_PATH}...")
    with open(IDS_PATH, "w") as f:
        json.dump(paper_ids, f)

    print("\nDone! Index built successfully.")
    print(f"  - Index: {INDEX_PATH}")
    print(f"  - IDs: {IDS_PATH}")


if __name__ == "__main__":
    build_index()
