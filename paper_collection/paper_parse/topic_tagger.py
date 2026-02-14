#!/usr/bin/python3
"""
Topic tagger for papers database.

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
"""

import argparse
import os
import re
import sqlite3

# Database path (relative to script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "..", "web_interface", "data")
DB_PATH = os.path.join(DATA_DIR, "papers.db")

# Topics: tag -> (full_name, exact_match_queries)
# exact_match_queries: case-insensitive substring match on title or abstract
TOPICS = {
    "Pretraining": ("LLM pre-train", ["mid-training", "pretraining", "pre-training"]),
    "RL": (
        "Reinforcement learning",
        ["reinforcement learning", "RLHF", "DPO", "GRPO"],
    ),
    "Reasoning": ("Reasoning", ["Reasoning", "Planning"]),
    "Factuality": ("Factuality, Hallucination", ["Factuality", "Hallucination"]),
    "RAG": (
        "RAG (Retrieval-Augmented Generation)",
        ["Retrieval-Augmented", "retrieval augmented"],
    ),
    "Agent": ("Agentic AI", ["agent", "agentic", "Tool use"]),
    "P13N": ("Personalization", ["personalization", "personalized"]),
    "Memory": ("Memory", ["Memory"]),
    "KG": ("Knowledge Graph", ["Knowledge Graph"]),
    "QA": ("Question Answering", ["Question Answering"]),
    "Recommendation": ("Recommendation", ["Recommendation", "recommender"]),
    "MM": ("Multi-Modal", ["multi-modal", "multimodal", "vision-language"]),
    "Speech": ("Speech", ["speech", "spoken"]),
    "Benchmark": ("Benchmark", ["benchmark"]),
}

# Short acronyms that need word-boundary matching to avoid false positives
SHORT_ACRONYMS = {"RL", "RAG", "KG", "QA", "MM"}


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


def exact_match_search(cursor, queries, paper_data=None):
    """Find papers that contain any of the queries in title or abstract (case insensitive).

    For short terms (<=3 chars), uses word boundary matching to avoid false positives
    like matching 'RAG' in 'leverages' or 'RL' in 'early'.
    For longer terms, uses substring matching.
    """
    matching_ids = set()

    # Get paper data if not provided
    if paper_data is None:
        cursor.execute("SELECT id, title, abstract FROM papers")
        paper_data = cursor.fetchall()

    for query in queries:
        query_lower = query.lower()

        if len(query) <= 3 or query.upper() in SHORT_ACRONYMS:
            # Use word boundary regex for short acronyms
            pattern = re.compile(r"\b" + re.escape(query_lower) + r"\b", re.IGNORECASE)
            for paper_id, title, abstract in paper_data:
                text = (title or "") + " " + (abstract or "")
                if pattern.search(text):
                    matching_ids.add(paper_id)
        else:
            # Use substring match for longer terms
            for paper_id, title, abstract in paper_data:
                title_lower = (title or "").lower()
                abstract_lower = (abstract or "").lower()
                if query_lower in title_lower or query_lower in abstract_lower:
                    matching_ids.add(paper_id)

    return matching_ids


def auto_tag_papers():
    """Auto-tag papers using exact match search."""
    print(f"Database: {DB_PATH}")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all papers with their text
    cursor.execute("SELECT id, title, abstract FROM papers")
    all_papers = cursor.fetchall()

    # Get all paper IDs for tracking
    all_paper_ids = [p[0] for p in all_papers]

    # Dictionary to track topics for each paper: paper_id -> set of topics
    paper_topics = {pid: set() for pid in all_paper_ids}

    # For each topic, run search
    print("\nTagging papers...")
    for tag, (full_name, exact_queries) in TOPICS.items():
        print(f"\n  {tag} ({full_name}):")
        tag_paper_ids = set()

        # Exact match search
        if exact_queries:
            exact_matches = exact_match_search(cursor, exact_queries, all_papers)
            tag_paper_ids.update(exact_matches)
            print(f"    Exact match {exact_queries}: {len(exact_matches)} papers")

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
    print(f"Re-tagging topic: {tag_to_retag}")

    full_name, exact_queries = TOPICS[tag_to_retag]

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
    print("Mode: Tagging only NEW papers (without topics)")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get only papers WITHOUT topics
    cursor.execute(
        "SELECT id, title, abstract FROM papers WHERE topic IS NULL OR topic = ''"
    )
    new_papers = cursor.fetchall()

    if not new_papers:
        print("\nNo new papers to tag.")
        conn.close()
        return

    new_paper_ids = [p[0] for p in new_papers]
    print(f"\nFound {len(new_paper_ids)} papers without topics")

    # Dictionary to track topics for each new paper: paper_id -> set of topics
    paper_topics = {pid: set() for pid in new_paper_ids}

    # For each topic, run search
    print("\nTagging new papers...")
    for tag, (full_name, exact_queries) in TOPICS.items():
        tag_paper_ids = set()

        # Exact match search (only for new papers)
        if exact_queries:
            matches = exact_match_search(cursor, exact_queries, new_papers)
            tag_paper_ids.update(matches)

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
