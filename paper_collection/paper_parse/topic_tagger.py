#!/usr/bin/python3
"""
Migration script to add 'topic' column to the papers database.

Topics (tag - full_name; exact_match; semantic_search):
    Pretraining - LLM pre-train; "mid-training"; "pretraining"
    RL - Reinforcement learning; "reinforcement learning", "RL", "RLHF", "DPO", "GRPO"; (empty)
    Reasoning - Reasoning; "Reasoning", "Planning"; (empty)
    Factuality - Factuality, Hallucination; (empty); "Factuality", "Hallucination"
    RAG - RAG (Retrieval-Augmented Generation); "RAG", "Retrieval-Augmented Generation"; (empty)
    Agent - Agentic AI; "agent", "agentic"; "Tool use", "Agentic AI"
    P13N - Personalization; "personalization"; (empty)
    Memory - Memory; "Memory"; (empty)
    KG - Knowledge Graph; "KG", "Knowledge Graph"; (empty)
    QA - Question Answering; "QA", "Question Answering"; (empty)
    Recommendation - Recommendation; (empty); "Recommendation"
    MM - Multi-Modal; (empty); "multi-modal", "visual"
    Speech - Speech; "speech"; (empty)
    Benchmark - Benchmark; "benchmark"; (empty)

Usage:
    python3 add_topic_column.py           # Add column and show stats
    python3 add_topic_column.py --tag     # Auto-tag ALL papers using both exact match and semantic search
    python3 add_topic_column.py --tag-new # Only tag papers without topics (for daily updates)
    python3 add_topic_column.py --retag KG  # Re-tag only specific topic, keep others
"""

import argparse
import json
import os
import re
import sqlite3

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# Database and index paths (relative to script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "..", "web_interface", "data")
DB_PATH = os.path.join(DATA_DIR, "papers.db")
INDEX_PATH = os.path.join(DATA_DIR, "papers.index")
IDS_PATH = os.path.join(DATA_DIR, "paper_ids.json")

# Model for semantic search
MODEL_NAME = "all-MiniLM-L6-v2"

# Score threshold for semantic search tagging
SCORE_THRESHOLD = 0.2

# Topics: tag -> (full_name, exact_match_queries, semantic_search_queries)
# exact_match_queries: case-insensitive substring match on title or abstract
# semantic_search_queries: FAISS semantic similarity search
TOPICS = {
    "Pretraining": ("LLM pre-train", ["mid-training"], ["pretraining"]),
    "RL": (
        "Reinforcement learning",
        ["reinforcement learning", "RL", "RLHF", "DPO", "GRPO"],
        [],
    ),
    "Reasoning": ("Reasoning", ["Reasoning", "Planning"], []),
    "Factuality": ("Factuality, Hallucination", [], ["Factuality", "Hallucination"]),
    "RAG": (
        "RAG (Retrieval-Augmented Generation)",
        ["RAG", "Retrieval-Augmented Generation"],
        [],
    ),
    "Agent": ("Agentic AI", ["agent", "agentic"], ["Tool use", "Agentic AI"]),
    "P13N": ("Personalization", [], ["personalization"]),
    "Memory": ("Memory", ["Memory"], []),
    "KG": ("Knowledge Graph", ["KG", "Knowledge Graph"], []),
    "QA": ("Question Answering", ["QA", "Question Answering"], []),
    "Recommendation": ("Recommendation", [], ["Recommendation"]),
    "MM": ("Multi-Modal", [], ["multi-modal", "visual"]),
    "Speech": ("Speech", ["speech"], []),
    "Benchmark": ("Benchmark", ["benchmark"], []),
}


def add_topic_column():
    """Add the topic column to the papers table if it doesn't exist."""
    print(f"Database: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(papers)")
    columns = [col[1] for col in cursor.fetchall()]

    if "topic" in columns:
        print("Column 'topic' already exists.")
    else:
        print("Adding 'topic' column...")
        cursor.execute("ALTER TABLE papers ADD COLUMN topic TEXT")
        conn.commit()
        print("Column 'topic' added successfully.")

    # Show current stats
    cursor.execute("SELECT COUNT(*) FROM papers")
    total = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM papers WHERE topic IS NOT NULL AND topic != ''"
    )
    with_topic = cursor.fetchone()[0]

    print(f"\nTotal papers: {total}")
    print(f"Papers with topic: {with_topic}")
    print(f"Papers without topic: {total - with_topic}")

    print(f"\nValid topics: {', '.join(TOPICS.keys())}")

    conn.close()


def show_topic_stats():
    """Show statistics about topics in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT topic, COUNT(*) as count
        FROM papers
        GROUP BY topic
        ORDER BY count DESC
    """
    )

    print("\nTopic distribution:")
    for row in cursor.fetchall():
        topic = row[0] or "(no topic)"
        count = row[1]
        print(f"  {topic}: {count}")

    conn.close()


def exact_match_search(cursor, queries):
    """Find papers that contain any of the queries in title or abstract (case insensitive).

    For short terms (<=3 chars), uses word boundary matching to avoid false positives
    like matching 'RAG' in 'leverages' or 'RL' in 'early'.
    For longer terms, uses substring matching.
    """
    matching_ids = set()

    # First, fetch all papers with their text
    cursor.execute("SELECT id, title, abstract FROM papers")
    all_papers = cursor.fetchall()

    for query in queries:
        query_lower = query.lower()

        if len(query) <= 3:
            # Use word boundary regex for short acronyms
            # \b matches word boundaries (start/end of word)
            pattern = re.compile(r"\b" + re.escape(query_lower) + r"\b", re.IGNORECASE)
            for paper_id, title, abstract in all_papers:
                text = (title or "") + " " + (abstract or "")
                if pattern.search(text):
                    matching_ids.add(paper_id)
        else:
            # Use substring match for longer terms
            for paper_id, title, abstract in all_papers:
                title_lower = (title or "").lower()
                abstract_lower = (abstract or "").lower()
                if query_lower in title_lower or query_lower in abstract_lower:
                    matching_ids.add(paper_id)

    return matching_ids


def semantic_search(model, index, paper_ids, queries, threshold):
    """Find papers using FAISS semantic similarity search."""
    matching_ids = set()
    for query in queries:
        query_embedding = model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_embedding)
        scores, indices = index.search(query_embedding, len(paper_ids))
        for i, score in zip(indices[0], scores[0]):
            if score >= threshold and i < len(paper_ids):
                matching_ids.add(paper_ids[i])
    return matching_ids


def auto_tag_papers():
    """Auto-tag papers using exact match and semantic search."""
    print(f"Database: {DB_PATH}")
    print(f"Index: {INDEX_PATH}")
    print(f"Score threshold for semantic search: {SCORE_THRESHOLD}")

    # Check if index exists (needed for semantic search)
    has_index = os.path.exists(INDEX_PATH) and os.path.exists(IDS_PATH)

    index = None
    paper_ids = None
    model = None

    if has_index:
        print("\nLoading FAISS index...")
        index = faiss.read_index(INDEX_PATH)
        with open(IDS_PATH, "r") as f:
            paper_ids = json.load(f)
        print(f"Index loaded with {index.ntotal} vectors")

        print(f"Loading model: {MODEL_NAME}...")
        model = SentenceTransformer(MODEL_NAME)
    else:
        print("\nWarning: FAISS index not found. Semantic search will be skipped.")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all paper IDs for tracking
    cursor.execute("SELECT id FROM papers")
    all_paper_ids = [row[0] for row in cursor.fetchall()]

    # Dictionary to track topics for each paper: paper_id -> set of topics
    paper_topics = {pid: set() for pid in all_paper_ids}

    # For each topic, run both search strategies
    print("\nTagging papers...")
    for tag, (full_name, exact_queries, semantic_queries) in TOPICS.items():
        print(f"\n  {tag} ({full_name}):")
        tag_paper_ids = set()

        # Exact match search
        if exact_queries:
            exact_matches = exact_match_search(cursor, exact_queries)
            tag_paper_ids.update(exact_matches)
            print(f"    Exact match {exact_queries}: {len(exact_matches)} papers")

        # Semantic search
        if semantic_queries and has_index:
            for query in semantic_queries:
                query_embedding = model.encode([query], convert_to_numpy=True)
                faiss.normalize_L2(query_embedding)
                scores, indices = index.search(query_embedding, len(paper_ids))

                matched = 0
                for i, score in zip(indices[0], scores[0]):
                    if score >= SCORE_THRESHOLD and i < len(paper_ids):
                        tag_paper_ids.add(paper_ids[i])
                        matched += 1
                print(f"    Semantic '{query}': {matched} papers")

        # Add tag to matched papers
        for paper_id in tag_paper_ids:
            if paper_id in paper_topics:
                paper_topics[paper_id].add(tag)

        print(f"    Total unique papers for {tag}: {len(tag_paper_ids)}")

    # Update database
    print("\nUpdating database...")
    updated = 0
    for paper_id, topics in paper_topics.items():
        if topics:
            topic_str = ", ".join(sorted(topics))
            cursor.execute(
                "UPDATE papers SET topic = ? WHERE id = ?", (topic_str, paper_id)
            )
            updated += 1
        else:
            cursor.execute("UPDATE papers SET topic = NULL WHERE id = ?", (paper_id,))

    conn.commit()
    conn.close()

    print(f"Updated {updated} papers with topics")

    # Show stats
    show_topic_stats()


def retag_single_topic(tag_to_retag):
    """Re-tag papers for a single topic, keeping other tags intact."""
    if tag_to_retag not in TOPICS:
        print(f"Error: Unknown topic '{tag_to_retag}'")
        print(f"Valid topics: {', '.join(TOPICS.keys())}")
        return

    print(f"Database: {DB_PATH}")
    print(f"Index: {INDEX_PATH}")
    print(f"Score threshold for semantic search: {SCORE_THRESHOLD}")
    print(f"Re-tagging topic: {tag_to_retag}")

    full_name, exact_queries, semantic_queries = TOPICS[tag_to_retag]

    # Check if index exists (needed for semantic search)
    has_index = os.path.exists(INDEX_PATH) and os.path.exists(IDS_PATH)

    index = None
    paper_ids = None
    model = None

    if has_index and semantic_queries:
        print("\nLoading FAISS index...")
        index = faiss.read_index(INDEX_PATH)
        with open(IDS_PATH, "r") as f:
            paper_ids = json.load(f)
        print(f"Index loaded with {index.ntotal} vectors")

        print(f"Loading model: {MODEL_NAME}...")
        model = SentenceTransformer(MODEL_NAME)
    elif semantic_queries:
        print("\nWarning: FAISS index not found. Semantic search will be skipped.")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"\n  {tag_to_retag} ({full_name}):")
    matching_paper_ids = set()

    # Exact match search
    if exact_queries:
        exact_matches = exact_match_search(cursor, exact_queries)
        matching_paper_ids.update(exact_matches)
        print(f"    Exact match {exact_queries}: {len(exact_matches)} papers")

    # Semantic search
    if semantic_queries and has_index:
        for query in semantic_queries:
            query_embedding = model.encode([query], convert_to_numpy=True)
            faiss.normalize_L2(query_embedding)
            scores, indices = index.search(query_embedding, len(paper_ids))

            matched = 0
            for i, score in zip(indices[0], scores[0]):
                if score >= SCORE_THRESHOLD and i < len(paper_ids):
                    matching_paper_ids.add(paper_ids[i])
                    matched += 1
            print(f"    Semantic '{query}': {matched} papers")

    print(f"    Total unique papers for {tag_to_retag}: {len(matching_paper_ids)}")

    # Update database - remove old tag, add new tag where appropriate
    print("\nUpdating database...")

    # Get all papers with their current topics
    cursor.execute("SELECT id, topic FROM papers")
    all_papers = cursor.fetchall()

    updated = 0
    for paper_id, current_topic in all_papers:
        # Parse current topics
        if current_topic:
            topics = set(t.strip() for t in current_topic.split(","))
        else:
            topics = set()

        # Remove old tag
        topics.discard(tag_to_retag)

        # Add new tag if paper matches
        if paper_id in matching_paper_ids:
            topics.add(tag_to_retag)

        # Update database
        new_topic = ", ".join(sorted(topics)) if topics else None
        if new_topic != current_topic:
            cursor.execute(
                "UPDATE papers SET topic = ? WHERE id = ?", (new_topic, paper_id)
            )
            updated += 1

    conn.commit()
    conn.close()

    print(f"Updated {updated} papers")

    # Show stats
    show_topic_stats()


def tag_new_papers():
    """Tag only papers that don't have topics yet (for daily updates)."""
    print(f"Database: {DB_PATH}")
    print(f"Index: {INDEX_PATH}")
    print(f"Score threshold for semantic search: {SCORE_THRESHOLD}")
    print("Mode: Tagging only NEW papers (without topics)")

    # Check if index exists (needed for semantic search)
    has_index = os.path.exists(INDEX_PATH) and os.path.exists(IDS_PATH)

    index = None
    paper_ids = None
    model = None

    if has_index:
        print("\nLoading FAISS index...")
        index = faiss.read_index(INDEX_PATH)
        with open(IDS_PATH, "r") as f:
            paper_ids = json.load(f)
        print(f"Index loaded with {index.ntotal} vectors")

        print(f"Loading model: {MODEL_NAME}...")
        model = SentenceTransformer(MODEL_NAME)
    else:
        print("\nWarning: FAISS index not found. Semantic search will be skipped.")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get only papers WITHOUT topics
    cursor.execute("SELECT id FROM papers WHERE topic IS NULL OR topic = ''")
    new_paper_ids = [row[0] for row in cursor.fetchall()]

    if not new_paper_ids:
        print("\nNo new papers to tag.")
        conn.close()
        return

    print(f"\nFound {len(new_paper_ids)} papers without topics")

    # Dictionary to track topics for each new paper: paper_id -> set of topics
    paper_topics = {pid: set() for pid in new_paper_ids}
    new_paper_set = set(new_paper_ids)

    # For each topic, run both search strategies
    print("\nTagging new papers...")
    for tag, (full_name, exact_queries, semantic_queries) in TOPICS.items():
        tag_paper_ids = set()

        # Exact match search (only for new papers)
        if exact_queries:
            # Get text for new papers only
            placeholders = ",".join("?" * len(new_paper_ids))
            cursor.execute(
                f"SELECT id, title, abstract FROM papers WHERE id IN ({placeholders})",
                new_paper_ids,
            )
            new_papers_data = cursor.fetchall()

            for query in exact_queries:
                query_lower = query.lower()
                if len(query) <= 3:
                    pattern = re.compile(
                        r"\b" + re.escape(query_lower) + r"\b", re.IGNORECASE
                    )
                    for paper_id, title, abstract in new_papers_data:
                        text = (title or "") + " " + (abstract or "")
                        if pattern.search(text):
                            tag_paper_ids.add(paper_id)
                else:
                    for paper_id, title, abstract in new_papers_data:
                        title_lower = (title or "").lower()
                        abstract_lower = (abstract or "").lower()
                        if query_lower in title_lower or query_lower in abstract_lower:
                            tag_paper_ids.add(paper_id)

        # Semantic search (filter to new papers only)
        if semantic_queries and has_index:
            for query in semantic_queries:
                query_embedding = model.encode([query], convert_to_numpy=True)
                faiss.normalize_L2(query_embedding)
                scores, indices = index.search(query_embedding, len(paper_ids))

                for i, score in zip(indices[0], scores[0]):
                    if score >= SCORE_THRESHOLD and i < len(paper_ids):
                        pid = paper_ids[i]
                        if pid in new_paper_set:
                            tag_paper_ids.add(pid)

        # Add tag to matched papers
        for paper_id in tag_paper_ids:
            if paper_id in paper_topics:
                paper_topics[paper_id].add(tag)

        if tag_paper_ids:
            print(f"  {tag}: {len(tag_paper_ids)} new papers")

    # Update database
    print("\nUpdating database...")
    updated = 0
    for paper_id, topics in paper_topics.items():
        if topics:
            topic_str = ", ".join(sorted(topics))
            cursor.execute(
                "UPDATE papers SET topic = ? WHERE id = ?", (topic_str, paper_id)
            )
            updated += 1

    conn.commit()
    conn.close()

    print(f"Tagged {updated} new papers with topics")


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Manage topic column in papers database."
    )
    parser.add_argument(
        "--tag",
        action="store_true",
        help="Auto-tag ALL papers using semantic search",
    )
    parser.add_argument(
        "--tag-new",
        action="store_true",
        help="Only tag papers without topics (for daily updates)",
    )
    parser.add_argument(
        "--retag",
        type=str,
        metavar="TOPIC",
        help="Re-tag only a specific topic, keeping other tags",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Always ensure column exists
    add_topic_column()

    if args.tag:
        auto_tag_papers()
    elif args.tag_new:
        tag_new_papers()
    elif args.retag:
        retag_single_topic(args.retag)
    else:
        show_topic_stats()
