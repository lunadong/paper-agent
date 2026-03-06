#!/usr/bin/python3
"""
Topic tagger for papers database (PostgreSQL).

Topics (tag - full_name; exact_match):
    Pretraining - LLM pre-train; "mid-training", "pretraining"
    RL - Reinforcement learning; "reinforcement learning", "RL", "RLHF", "DPO", "GRPO"
    Reasoning - Reasoning; "Reasoning", "Planning"
    Factuality - Factuality, Hallucination; "Factuality", "Hallucination"
    RAG - RAG (Retrieval-Augmented Generation); "RAG", "Retrieval-Augmented Generation"
    Agent - Agentic AI; "agent", "agentic", "Tool use"
    P13N - Personalization; "personalization"
    Memory - Memory; "Memory"
    KG - Knowledge Graph; "KG", "Knowledge Graph"
    QA - Question Answering; "QA", "Question Answering"
    Recommendation - Recommendation; "Recommendation"
    MM - Multi-Modal; "multi-modal", "visual", "multimodal"
    Speech - Speech; "speech"
    Benchmark - Benchmark; "benchmark"

Usage:
    python3 topic_tagger.py           # Show stats
    python3 topic_tagger.py --tag     # Auto-tag ALL papers using exact match
    python3 topic_tagger.py --tag-new # Only tag papers without topics (for daily updates)
    python3 topic_tagger.py --retag KG  # Re-tag only specific topic, keep others
    python3 topic_tagger.py --set-primary 123:Agent  # Force set primary_topic for paper ID 123
    python3 topic_tagger.py --set-primary 123:      # Clear primary_topic for paper ID 123
"""

import argparse
import os
import re
import sys
from typing import Optional

# Add parent directories for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PAPER_COLLECTION_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PAPER_COLLECTION_DIR)

from paper_db import PaperDB, TOPICS

# Search queries for each topic: tag -> (exact_match_queries, semantic_queries)
# - exact_match_queries: case-insensitive substring match on title or abstract
# - semantic_queries: vector similarity search using pgvector
# Topic full names are defined in paper_db.py (TOPICS dictionary)
TOPIC_QUERIES = {
    "Pretraining": (
        ["mid-training"],
        ["pre-training"],
    ),
    "RL": (
        ["reinforcement learning", "RLHF", "DPO", "GRPO"],
        [],
    ),
    "Reasoning": (
        ["Reasoning", "Planning"],
        [],
    ),
    "Factuality": (
        [],
        ["Factuality", "Hallucination"],
    ),
    "RAG": (
        ["RAG", "retrieval-augmented generation"],
        [],
    ),
    "Agent": (
        ["agent", "agentic"],
        ["tool use", "agentic AI"],
    ),
    "P13N": (
        [],
        ["personalization"],
    ),
    "Memory": (
        ["Memory"],
        [],
    ),
    "KG": (
        ["Knowledge Graph", "KG"],
        [],
    ),
    "QA": (
        ["Question Answering", "QA"],
        [],
    ),
    "Recommendation": (
        [],
        ["recommendation"],
    ),
    "MM": (
        [],
        ["multi-modal", "visual"],
    ),
    "Speech": (
        ["speech", "spoken"],
        [],
    ),
    "Benchmark": (
        ["benchmark"],
        [],
    ),
}

# Short acronyms that need word-boundary matching to avoid false positives
SHORT_ACRONYMS = {"RL", "RAG", "KG", "QA", "MM"}

# Semantic search threshold (cosine similarity)
SEMANTIC_THRESHOLD = 0.5


def exact_match_search(papers, queries):
    """Find papers that contain any of the queries in title or abstract (case insensitive).

    For short terms (<=3 chars), uses word boundary matching to avoid false positives
    like matching 'RAG' in 'leverages' or 'RL' in 'early'.
    For longer terms, uses substring matching.
    """
    matching_ids = set()

    for query in queries:
        query_lower = query.lower()

        if len(query) <= 3 or query.upper() in SHORT_ACRONYMS:
            # Use word boundary regex for short acronyms
            pattern = re.compile(r"\b" + re.escape(query_lower) + r"\b", re.IGNORECASE)
            for paper in papers:
                text = (paper.get("title") or "") + " " + (paper.get("abstract") or "")
                if pattern.search(text):
                    matching_ids.add(paper["id"])
        else:
            # Use substring match for longer terms
            for paper in papers:
                title_lower = (paper.get("title") or "").lower()
                abstract_lower = (paper.get("abstract") or "").lower()
                if query_lower in title_lower or query_lower in abstract_lower:
                    matching_ids.add(paper["id"])

    return matching_ids


def semantic_search(db, queries, limit_per_query=50):
    """Find papers using vector similarity search via pgvector.

    Args:
        db: PaperDB instance
        queries: List of semantic query strings
        limit_per_query: Max results per query

    Returns:
        Set of matching paper IDs
    """
    matching_ids = set()

    for query in queries:
        try:
            results = db.vector_search(
                query, limit=limit_per_query, threshold=SEMANTIC_THRESHOLD
            )
            for r in results:
                matching_ids.add(r["id"])
        except Exception as e:
            print(f"    Warning: Semantic search failed for '{query}': {e}")

    return matching_ids


def show_topic_stats():
    """Show statistics about topics in the database."""
    print("Connecting to PostgreSQL database...")
    db = PaperDB()

    papers = db.get_all_papers()
    total = len(papers)

    # Count topics
    topic_counts = {}
    no_topic_count = 0

    for paper in papers:
        topics = paper.get("topics")
        if topics:
            topic_counts[topics] = topic_counts.get(topics, 0) + 1
        else:
            no_topic_count += 1

    print(f"\nTotal papers: {total}")
    print(f"Papers with topic: {total - no_topic_count}")
    print(f"Papers without topic: {no_topic_count}")

    print("\nTopic distribution:")
    for topic, count in sorted(topic_counts.items(), key=lambda x: -x[1]):
        print(f"  {topic}: {count}")

    if no_topic_count > 0:
        print(f"  (no topic): {no_topic_count}")

    db.close()


def auto_tag_papers():
    """Auto-tag papers using exact match search."""
    print("Connecting to PostgreSQL database...")
    db = PaperDB()

    papers = db.get_all_papers()
    print(f"Total papers: {len(papers)}")

    # Dictionary to track topics for each paper: paper_id -> set of topics
    paper_topics = {p["id"]: set() for p in papers}

    # For each topic, run search
    print("\nTagging papers...")
    for tag, (exact_queries, semantic_queries) in TOPIC_QUERIES.items():
        full_name = TOPICS.get(tag, tag)
        print(f"\n  {tag} ({full_name}):")
        tag_paper_ids = set()

        # Exact match search
        if exact_queries:
            exact_matches = exact_match_search(papers, exact_queries)
            tag_paper_ids.update(exact_matches)
            print(f"    Exact match: {len(exact_matches)} papers")

        # Semantic search
        if semantic_queries:
            semantic_matches = semantic_search(db, semantic_queries)
            new_semantic = semantic_matches - tag_paper_ids
            tag_paper_ids.update(semantic_matches)
            print(
                f"    Semantic search: {len(semantic_matches)} papers ({len(new_semantic)} new)"
            )

        # Add tag to matched papers
        for paper_id in tag_paper_ids:
            if paper_id in paper_topics:
                paper_topics[paper_id].add(tag)

        print(f"    Total unique papers for {tag}: {len(tag_paper_ids)}")

    # Update database
    print("\nUpdating database...")
    updated = 0
    for paper_id, topics in paper_topics.items():
        topic_str = ", ".join(sorted(topics)) if topics else None
        if db.update_paper(paper_id, topics=topic_str):
            updated += 1

    db.close()
    print(f"Updated {updated} papers with topics")

    # Show stats
    show_topic_stats()


def retag_single_topic(tag_to_retag):
    """Re-tag papers for a single topic, keeping other tags intact."""
    if tag_to_retag not in TOPIC_QUERIES:
        print(f"Error: Unknown topic '{tag_to_retag}'")
        print(f"Valid topics: {', '.join(TOPIC_QUERIES.keys())}")
        return

    print("Connecting to PostgreSQL database...")
    print(f"Re-tagging topic: {tag_to_retag}")

    exact_queries, semantic_queries = TOPIC_QUERIES[tag_to_retag]
    full_name = TOPICS.get(tag_to_retag, tag_to_retag)
    db = PaperDB()
    papers = db.get_all_papers()

    print(f"\n  {tag_to_retag} ({full_name}):")
    matching_paper_ids = set()

    # Exact match search
    if exact_queries:
        exact_matches = exact_match_search(papers, exact_queries)
        matching_paper_ids.update(exact_matches)
        print(f"    Exact match: {len(exact_matches)} papers")

    # Semantic search
    if semantic_queries:
        semantic_matches = semantic_search(db, semantic_queries)
        new_semantic = semantic_matches - matching_paper_ids
        matching_paper_ids.update(semantic_matches)
        print(
            f"    Semantic search: {len(semantic_matches)} papers ({len(new_semantic)} new)"
        )

    print(f"    Total unique papers for {tag_to_retag}: {len(matching_paper_ids)}")

    # Update database - remove old tag, add new tag where appropriate
    print("\nUpdating database...")

    updated = 0
    for paper in papers:
        paper_id = paper["id"]
        current_topic = paper.get("topics") or ""

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
            db.update_paper(paper_id, topics=new_topic)
            updated += 1

    db.close()
    print(f"Updated {updated} papers")

    # Show stats
    show_topic_stats()


def set_primary_topic(paper_id: int, topic: Optional[str]):
    """Force set the primary_topic for a specific paper.

    Args:
        paper_id: The paper's database ID
        topic: The topic to set (must be a valid topic tag), or None to clear
    """
    # Validate topic if provided
    if topic and topic not in TOPICS:
        print(f"Error: Unknown topic '{topic}'")
        print(f"Valid topics: {', '.join(sorted(TOPICS.keys()))}")
        return False

    print("Connecting to PostgreSQL database...")
    db = PaperDB()

    # Get the paper to verify it exists
    paper = db.get_paper_by_id(paper_id)
    if not paper:
        print(f"Error: Paper with ID {paper_id} not found")
        db.close()
        return False

    # Show paper info
    title = paper.get("title", "N/A")[:60]
    current_primary = paper.get("primary_topic") or "(none)"
    current_topics = paper.get("topics") or "(none)"

    print(f"\nPaper ID: {paper_id}")
    print(f"Title: {title}...")
    print(f"Current topics: {current_topics}")
    print(f"Current primary_topic: {current_primary}")

    # Update primary_topic
    new_primary = topic if topic else None
    if db.update_paper(paper_id, primary_topic=new_primary):
        if new_primary:
            print(f"\n[OK] Set primary_topic to '{new_primary}'")
        else:
            print("\n[OK] Cleared primary_topic")
        db.close()
        return True
    else:
        print("\n[X] Failed to update primary_topic")
        db.close()
        return False


def tag_new_papers():
    """Tag only papers that don't have topics yet (for daily updates)."""
    print("Connecting to PostgreSQL database...")
    print("Mode: Tagging only NEW papers (without topics)")

    db = PaperDB()
    papers = db.get_all_papers()

    # Filter to papers WITHOUT topics
    new_papers = [p for p in papers if not p.get("topics")]

    if not new_papers:
        print("\nNo new papers to tag.")
        db.close()
        return

    print(f"\nFound {len(new_papers)} papers without topics")

    # Dictionary to track topics for each new paper: paper_id -> set of topics
    paper_topics = {p["id"]: set() for p in new_papers}

    # For each topic, run search
    print("\nTagging new papers...")
    for tag, (exact_queries, semantic_queries) in TOPIC_QUERIES.items():
        tag_paper_ids = set()

        # Exact match search (only for new papers)
        if exact_queries:
            exact_matches = exact_match_search(new_papers, exact_queries)
            tag_paper_ids.update(exact_matches)

        # Semantic search
        if semantic_queries:
            semantic_matches = semantic_search(db, semantic_queries)
            # Filter to only new papers
            semantic_matches = semantic_matches & set(paper_topics.keys())
            tag_paper_ids.update(semantic_matches)

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
            if db.update_paper(paper_id, topic=topic_str):
                updated += 1

    db.close()
    print(f"Tagged {updated} new papers with topics")


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Manage topic column in papers database."
    )
    parser.add_argument(
        "--tag",
        action="store_true",
        help="Auto-tag ALL papers using exact match search",
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
    parser.add_argument(
        "--set-primary",
        type=str,
        metavar="ID:TOPIC",
        help="Force set primary_topic for a paper (e.g., '123:Agent' or '123:' to clear)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.tag:
        auto_tag_papers()
    elif args.tag_new:
        tag_new_papers()
    elif args.retag:
        retag_single_topic(args.retag)
    elif args.set_primary:
        # Parse ID:TOPIC format
        if ":" not in args.set_primary:
            print("Error: --set-primary requires format 'ID:TOPIC' (e.g., '123:Agent')")
            print("       Use 'ID:' to clear the primary_topic (e.g., '123:')")
            sys.exit(1)
        paper_id_str, topic = args.set_primary.split(":", 1)
        try:
            paper_id = int(paper_id_str)
        except ValueError:
            print(f"Error: Invalid paper ID '{paper_id_str}' - must be an integer")
            sys.exit(1)
        # Empty topic means clear
        topic = topic.strip() if topic.strip() else None
        if not set_primary_topic(paper_id, topic):
            sys.exit(1)
    else:
        show_topic_stats()
