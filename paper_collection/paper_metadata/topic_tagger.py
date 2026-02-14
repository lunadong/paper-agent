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
"""

import argparse
import os
import re
import sys

# Add parent directories for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PAPER_COLLECTION_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PAPER_COLLECTION_DIR)

from paper_db import PaperDB

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
        topic = paper.get("topic")
        if topic:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
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
    for tag, (full_name, exact_queries) in TOPICS.items():
        print(f"\n  {tag} ({full_name}):")
        tag_paper_ids = set()

        # Exact match search
        if exact_queries:
            exact_matches = exact_match_search(papers, exact_queries)
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
        topic_str = ", ".join(sorted(topics)) if topics else None
        if db.update_paper(paper_id, topic=topic_str):
            updated += 1

    db.close()
    print(f"Updated {updated} papers with topics")

    # Show stats
    show_topic_stats()


def retag_single_topic(tag_to_retag):
    """Re-tag papers for a single topic, keeping other tags intact."""
    if tag_to_retag not in TOPICS:
        print(f"Error: Unknown topic '{tag_to_retag}'")
        print(f"Valid topics: {', '.join(TOPICS.keys())}")
        return

    print("Connecting to PostgreSQL database...")
    print(f"Re-tagging topic: {tag_to_retag}")

    full_name, exact_queries = TOPICS[tag_to_retag]
    db = PaperDB()
    papers = db.get_all_papers()

    print(f"\n  {tag_to_retag} ({full_name}):")
    matching_paper_ids = set()

    # Exact match search
    if exact_queries:
        exact_matches = exact_match_search(papers, exact_queries)
        matching_paper_ids.update(exact_matches)
        print(f"    Exact match {exact_queries}: {len(exact_matches)} papers")

    print(f"    Total unique papers for {tag_to_retag}: {len(matching_paper_ids)}")

    # Update database - remove old tag, add new tag where appropriate
    print("\nUpdating database...")

    updated = 0
    for paper in papers:
        paper_id = paper["id"]
        current_topic = paper.get("topic") or ""

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
            db.update_paper(paper_id, topic=new_topic)
            updated += 1

    db.close()
    print(f"Updated {updated} papers")

    # Show stats
    show_topic_stats()


def tag_new_papers():
    """Tag only papers that don't have topics yet (for daily updates)."""
    print("Connecting to PostgreSQL database...")
    print("Mode: Tagging only NEW papers (without topics)")

    db = PaperDB()
    papers = db.get_all_papers()

    # Filter to papers WITHOUT topics
    new_papers = [p for p in papers if not p.get("topic")]

    if not new_papers:
        print("\nNo new papers to tag.")
        db.close()
        return

    print(f"\nFound {len(new_papers)} papers without topics")

    # Dictionary to track topics for each new paper: paper_id -> set of topics
    paper_topics = {p["id"]: set() for p in new_papers}

    # For each topic, run search
    print("\nTagging new papers...")
    for tag, (full_name, exact_queries) in TOPICS.items():
        tag_paper_ids = set()

        # Exact match search (only for new papers)
        if exact_queries:
            matches = exact_match_search(new_papers, exact_queries)
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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.tag:
        auto_tag_papers()
    elif args.tag_new:
        tag_new_papers()
    elif args.retag:
        retag_single_topic(args.retag)
    else:
        show_topic_stats()
