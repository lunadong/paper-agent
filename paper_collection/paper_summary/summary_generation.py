#!/usr/bin/env python3
"""
Paper Summary Generation using LLM APIs

This script generates structured JSON summaries of research papers using
LLM APIs (Google Gemini via wearables-ape.io or Google AI Studio).

Setup:
    1. Install the required packages:
       pip install requests pyyaml PyPDF2
       # For Google API: pip install google-generativeai

    2. Set your API key in config.yaml or as environment variable:
       export GEMINI_API_KEY="your-api-key"

Usage:
    python summary_generation.py --pdf-url "https://arxiv.org/pdf/2501.15228"
    python summary_generation.py --pdf-url "URL" --model "gemini-1.5-pro"
    python summary_generation.py --help
"""

import argparse
import json
from pathlib import Path
from typing import Optional

# Handle both direct execution and package import
try:
    # When imported as a package
    from .prompt_manager import ALLOWED_TOPICS, load_prompt_template, load_topic_prompt
    from .util.arxiv_html_processing import (
        download_arxiv_html_with_figures,
        get_arxiv_id_from_url,
        is_arxiv_url,
    )
    from .util.checkpoint import (
        CheckpointManager,
        is_shutdown_requested,
        RateLimiter,
        set_checkpoint_manager,
        set_rate_limiter,
        setup_signal_handlers,
    )
    from .util.llm_client import (
        call_gemini_api,
        get_default_model,
        get_lightweight_model,
    )
    from .util.pdf_processing import (
        download_pdf_bytes,
        download_pdf_text,
        extract_text_from_pdf_bytes,
        PDFCache,
        set_pdf_cache,
        store_figures_in_db,
    )
except ImportError:
    # When run directly as a script
    from prompt_manager import ALLOWED_TOPICS, load_prompt_template, load_topic_prompt
    from util.arxiv_html_processing import (
        download_arxiv_html_with_figures,
        get_arxiv_id_from_url,
        is_arxiv_url,
    )
    from util.checkpoint import (
        CheckpointManager,
        is_shutdown_requested,
        RateLimiter,
        set_checkpoint_manager,
        set_rate_limiter,
        setup_signal_handlers,
    )
    from util.llm_client import (
        call_gemini_api,
        get_default_model,
        get_lightweight_model,
    )
    from util.pdf_processing import (
        download_pdf_bytes,
        download_pdf_text,
        extract_text_from_pdf_bytes,
        PDFCache,
        set_pdf_cache,
        store_figures_in_db,
    )


# ==============================================================================
# Topic Classification and Summary Generation
# ==============================================================================
def _validate_topics(result: dict) -> dict:
    """
    Validate that topics are in the allowed list.
    If primary_topic is not in the list, set it to None.
    Filter out invalid topics from the topic list.
    """
    topics = result.get("topics", [])
    primary_topic = result.get("primary_topic")

    # Filter topics to only include allowed ones
    valid_topics = [t for t in topics if t in ALLOWED_TOPICS]
    invalid_topics = [t for t in topics if t not in ALLOWED_TOPICS]

    if invalid_topics:
        print(f"  Warning: Removing invalid topics: {invalid_topics}")

    # Check if primary_topic is valid
    if primary_topic and primary_topic not in ALLOWED_TOPICS:
        print(f"  Warning: Invalid primary_topic '{primary_topic}', setting to None")
        primary_topic = None

    result["topics"] = valid_topics
    result["primary_topic"] = primary_topic
    return result


def classify_paper_topics(
    paper_url: str,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    paper_text: Optional[str] = None,
) -> dict:
    """
    Stage 1: Classify paper topics and determine primary topic.

    Args:
        paper_url: URL to the paper (arXiv abstract, PDF, or HTML link)
        model_name: Gemini model to use (default: from config)
        api_key: API key. If None, uses default.
        paper_text: Pre-extracted paper text. If None, downloads and extracts.

    Returns:
        Dictionary with:
        - topic: list of topic tags (only from ALLOWED_TOPICS)
        - primary_topic: the main topic (None if invalid)
        - reasoning: explanation of the classification
    """
    if model_name is None:
        model_name = get_default_model()

    # Load topic classification prompt
    prompt_template = load_topic_prompt()

    # Use provided paper_text or download
    print(f"Classifying topics for: {paper_url}")
    if paper_text is None:
        paper_text = download_pdf_text(paper_url)

    # Build the prompt with actual paper content
    prompt = prompt_template.replace("<PAPER_URL>", paper_url)

    # Insert the paper content after the first line (which contains the URL)
    paper_content_section = (
        "\n\n========================\n"
        "Paper Content\n"
        f"========================\n\n{paper_text}\n\n"
    )
    # Insert after "Read the paper at: <url>" line
    first_newline = prompt.find("\n")
    if first_newline != -1:
        prompt = prompt[:first_newline] + paper_content_section + prompt[first_newline:]
    else:
        # Fallback: prepend content section
        prompt = paper_content_section + prompt

    print(f"  Using model: {model_name}")
    print(f"  Prompt length: {len(prompt)} characters")

    # Retry up to 3 times for LLM parsing errors
    max_llm_retries = 3
    response_text = ""
    for llm_attempt in range(max_llm_retries):
        response_text = call_gemini_api(prompt, model_name, api_key)

        # Try to parse as JSON
        try:
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1

            if json_start != -1 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
                # Validate topics are in the allowed list
                result = _validate_topics(result)
                print(f"  Topics: {result.get('topic', [])}")
                print(f"  Primary topic: {result.get('primary_topic', 'N/A')}")
                return result
            else:
                if llm_attempt < max_llm_retries - 1:
                    print(
                        f"  Warning: Could not find JSON in response, retrying... "
                        f"({llm_attempt + 1}/{max_llm_retries})"
                    )
                    continue
                print("  Warning: Could not find JSON in response after retries")
                return {
                    "topics": [],
                    "primary_topic": None,
                    "reasoning": response_text,
                }

        except json.JSONDecodeError as e:
            if llm_attempt < max_llm_retries - 1:
                print(
                    f"  Warning: Could not parse JSON: {e}, retrying... "
                    f"({llm_attempt + 1}/{max_llm_retries})"
                )
                continue
            print(f"  Warning: Could not parse JSON after retries: {e}")
            return {
                "topics": [],
                "primary_topic": None,
                "reasoning": response_text,
            }

    return {
        "topics": [],
        "primary_topic": None,
        "reasoning": response_text,
    }


def generate_paper_summary(
    paper_url: str,
    prompt_template: Optional[str] = None,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    paper_text: Optional[str] = None,
) -> dict:
    """
    Generate a structured summary for a paper given its URL.

    Args:
        paper_url: URL to the paper (arXiv abstract, PDF, or HTML link)
        prompt_template: Custom prompt template. If None, loads from prompt.txt
        model_name: Gemini model to use (default: from config)
        api_key: API key. If None, uses default.
        paper_text: Pre-extracted paper text. If None, downloads and extracts.

    Returns:
        Parsed JSON summary dictionary.
    """
    if model_name is None:
        model_name = get_default_model()

    # Load prompt template if not provided
    if prompt_template is None:
        prompt_template = load_prompt_template()

    # Use provided paper_text or download
    print(f"Generating summary for: {paper_url}")
    if paper_text is None:
        paper_text = download_pdf_text(paper_url)

    # Build the prompt with actual paper content
    prompt = prompt_template.replace("<PAPER_URL>", paper_url)

    # Insert the paper content after the first line (which contains the URL)
    paper_content_section = (
        "\n\n========================\n"
        "Paper Content\n"
        f"========================\n\n{paper_text}\n\n"
    )
    # Insert after "Read the paper at: <url>" line
    first_newline = prompt.find("\n")
    if first_newline != -1:
        prompt = prompt[:first_newline] + paper_content_section + prompt[first_newline:]
    else:
        # Fallback: prepend content section
        prompt = paper_content_section + prompt

    print(f"  Using model: {model_name}")
    print(f"  Prompt length: {len(prompt)} characters")

    response_text = call_gemini_api(prompt, model_name, api_key)

    # Try to parse as JSON
    try:
        # Find JSON in response (it might be wrapped in markdown code blocks)
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1

        if json_start != -1 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            return json.loads(json_str)
        else:
            print("  Warning: Could not find JSON in response")
            return {"raw_response": response_text}

    except json.JSONDecodeError as e:
        print(f"  Warning: Could not parse JSON: {e}")
        return {"raw_response": response_text}


def generate_summary_for_paper(
    paper_id: int,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    db=None,
    prompt_file: Optional[str] = None,
    output_dir: Optional[str] = None,
    save_db: bool = False,
    overwrite: bool = False,
) -> dict:
    """
    Generate summary for a paper using multi-stage approach.

    Args:
        paper_id: Database ID of the paper
        model_name: LLM model to use
        api_key: API key for the LLM
        db: Database connection (optional)
        prompt_file: File to save generated prompts for debugging
        output_dir: Directory to save all outputs (figures, summary JSON)
        save_db: Whether to save results to database
        overwrite: Whether to regenerate everything regardless of existing data

    Stages:
        Stage 0: PDF download (only if any later stage needs it)
        Stage 1: Figure extraction (only if figures don't exist in DB)
        Stage 2: Text extraction (only if Stage 3 or 4 need it)
        Stage 3: Topic classification (only if primary_topic doesn't exist)
        Stage 4: Summary generation (only if summary_generated_at doesn't exist)

    Conditional execution:
        - If overwrite=True, run all stages regardless of existing data
        - Skip PDF download (Stage 0) if no stages need it
        - Skip text extraction (Stage 2) if only figures are needed
    """
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from paper_db import PaperDB

    if model_name is None:
        model_name = get_default_model()

    result = {"success": False, "summary": None}
    topics = []
    primary_topic = None
    stages_run = []

    should_close = db is None
    if db is None:
        db = PaperDB()

    try:
        paper = db.get_paper_by_id(paper_id)
        if not paper:
            result["error"] = f"Paper with ID {paper_id} not found"
            return result

        title, link = paper.get("title", ""), paper.get("link", "")
        if not title or not link:
            result["error"] = f"Missing title or link for paper {paper_id}"
            return result

        pdf_url = link.replace("/abs/", "/pdf/") if "arxiv.org/abs/" in link else link
        if "arxiv.org" in pdf_url and not pdf_url.endswith(".pdf"):
            pdf_url += ".pdf"

        print(f"Processing paper ID {paper_id}: {title}...")

        # =================================================================
        # Setup output directory if specified
        # =================================================================
        paper_output_dir = None
        if output_dir:
            # Create directory structure: output_dir/paper_{id}/
            # Use arxiv_id if available, otherwise use paper_id
            arxiv_id = get_arxiv_id_from_url(link) if is_arxiv_url(link) else None
            dir_name = f"arxiv_{arxiv_id}" if arxiv_id else f"paper_{paper_id}"
            paper_output_dir = Path(output_dir) / dir_name
            paper_output_dir.mkdir(parents=True, exist_ok=True)
            print(f"  Output directory: {paper_output_dir}")

        # =================================================================
        # Determine which stages to run
        # =================================================================
        existing_images = db.get_paper_images(paper_id) if save_db else []

        if overwrite:
            # Overwrite mode: regenerate everything
            run_figures = True
            run_topics = True
            run_summary = True
        elif save_db:
            # Normal mode with DB: only run what's missing
            run_figures = not existing_images
            run_topics = not paper.get("primary_topic")
            run_summary = not paper.get("summary_generated_at")
        else:
            # Testing mode (no save_db, no overwrite): run topics and summary only
            run_figures = False
            run_topics = True
            run_summary = True

        # Derived indicators
        need_pdf = run_figures or run_topics or run_summary
        need_text = run_topics or run_summary

        print(
            f"  run_figures={run_figures}, run_topics={run_topics}, "
            f"run_summary={run_summary}"
        )
        print(f"  need_pdf={need_pdf}, need_text={need_text}")

        if not need_pdf:
            print("Nothing to do - all data already exists")
            result["success"] = True
            return result

        # =================================================================
        # Stage 0: Content Download (HTML for arXiv, PDF otherwise)
        # =================================================================
        print("\n========== Stage 0: Content Download ==========")
        stages_run.append("stage0_content_download")
        pdf_bytes = None
        paper_text = None
        html_figures = []
        use_abstract_fallback = False
        content_source = None  # "html", "pdf", or "abstract"

        # Try HTML extraction for arXiv papers first
        if is_arxiv_url(link):
            arxiv_id = get_arxiv_id_from_url(link)
            print(f"  arXiv paper detected (ID: {arxiv_id}), trying HTML extraction...")
            try:
                html_result = download_arxiv_html_with_figures(
                    url=link,
                    paper_id=str(paper_id),
                    extract_figures=run_figures,
                )
                if html_result.get("text"):
                    paper_text = html_result["text"]
                    html_figures = html_result.get("figures", [])
                    content_source = "html"
                    print(f"  HTML extraction successful: {len(paper_text)} chars")
            except Exception as e:
                print(f"  HTML extraction failed: {e}")
                print("  Falling back to PDF extraction...")

        # Fall back to PDF if HTML extraction failed or not arXiv
        if content_source is None:
            try:
                pdf_bytes = download_pdf_bytes(pdf_url)
                content_source = "pdf"
                print(f"  Downloaded {len(pdf_bytes)} bytes from PDF")
            except Exception as e:
                print(f"  PDF download failed: {e}")
                abstract = paper.get("abstract")
                if abstract and need_text:
                    print("  Falling back to abstract for topic classification...")
                    paper_text = f"Title: {title}\n\nAbstract:\n{abstract}"
                    use_abstract_fallback = True
                    content_source = "abstract"
                elif not need_text and run_figures:
                    # Only needed figures, but PDF failed
                    print("  Cannot extract figures without PDF or HTML")
                    run_figures = False
                else:
                    result["error"] = f"Content download failed, no abstract: {e}"
                    return result

        # =================================================================
        # Stage 1: Figure Extraction
        # =================================================================
        if run_figures:
            if html_figures:
                # Use figures already extracted from HTML
                print("\n========== Stage 1: Figure Extraction (HTML) ==========")
                stages_run.append("stage1_figures_html")
                print(f"  Using {len(html_figures)} figures from HTML extraction")

                # Save figures locally if output_dir specified
                if paper_output_dir:
                    figures_dir = paper_output_dir / "figures"
                    figures_dir.mkdir(exist_ok=True)
                    saved_count = 0
                    for fig in html_figures:
                        fig_name = fig.get("filename", f"figure_{saved_count}.png")
                        fig_data = fig.get("image_data")
                        if fig_data:
                            fig_path = figures_dir / fig_name
                            with open(fig_path, "wb") as f:
                                f.write(fig_data)
                            saved_count += 1
                    print(f"  Saved {saved_count} figures to {figures_dir}")

                if save_db:
                    try:
                        image_ids = store_figures_in_db(
                            paper_db_id=paper_id,
                            figures=html_figures,
                            store_image_data=True,
                        )
                        print(f"  Stored {len(image_ids)} figures in DB")
                    except Exception as e:
                        print(f"  Error storing HTML figures: {e}")
            elif pdf_bytes:
                # Fall back to PDF figure extraction
                print("\n========== Stage 1: Figure Extraction (PDF) ==========")
                stages_run.append("stage1_figures_pdf")
                try:
                    try:
                        from .util import figure_extraction_from_pdf as fig_module
                    except ImportError:
                        from util import figure_extraction_from_pdf as fig_module

                    if fig_module.PYMUPDF_AVAILABLE:
                        figures = fig_module.extract_figures_from_pdf_bytes(
                            pdf_bytes=pdf_bytes,
                            paper_id=str(paper_id),
                        )
                        if figures:
                            print(f"  Extracted {len(figures)} figures")

                            # Save figures locally if output_dir specified
                            if paper_output_dir:
                                figures_dir = paper_output_dir / "figures"
                                figures_dir.mkdir(exist_ok=True)
                                saved_count = 0
                                for fig in figures:
                                    fig_name = fig.get(
                                        "filename", f"figure_{saved_count}.png"
                                    )
                                    fig_data = fig.get("image_data")
                                    if fig_data:
                                        fig_path = figures_dir / fig_name
                                        with open(fig_path, "wb") as f:
                                            f.write(fig_data)
                                        saved_count += 1
                                print(f"  Saved {saved_count} figures to {figures_dir}")

                            if save_db:
                                image_ids = store_figures_in_db(
                                    paper_db_id=paper_id,
                                    figures=figures,
                                    store_image_data=True,
                                )
                                print(f"  Stored {len(image_ids)} figures in DB")
                        else:
                            print("  No figures found in PDF")
                    else:
                        print("  PyMuPDF not available, skipping")
                except Exception as e:
                    print(f"  Figure extraction error: {e}")
            else:
                print("\n========== Stage 1: Figure Extraction (SKIPPED) ==========")
                print("  No content source available for figures")
        else:
            print("\n========== Stage 1: Figure Extraction (SKIPPED) ==========")
            print("  Figures already exist or not requested")

        # =================================================================
        # Stage 2: Text Extraction
        # =================================================================
        if need_text and content_source == "html":
            print("\n========== Stage 2: Text Extraction (HTML) ==========")
            stages_run.append("stage2_text_html")
            print(f"  Already extracted {len(paper_text)} characters from HTML")
        elif need_text and pdf_bytes and not use_abstract_fallback:
            print("\n========== Stage 2: Text Extraction (PDF) ==========")
            stages_run.append("stage2_text_pdf")
            paper_text = extract_text_from_pdf_bytes(pdf_bytes)
            print(f"  Extracted {len(paper_text)} characters")
        elif need_text and use_abstract_fallback:
            print("\n========== Stage 2: Text Extraction (ABSTRACT) ==========")
            stages_run.append("stage2_text_abstract")
            text_len = len(paper_text) if paper_text else 0
            print(f"  Using abstract fallback ({text_len} chars)")
        elif not need_text:
            print("\n========== Stage 2: Text Extraction (SKIPPED) ==========")
            print("  Not needed (only figures requested)")

        # =================================================================
        # Stage 3: Topic Classification
        # =================================================================
        if run_topics:
            print("\n========== Stage 3: Topic Classification ==========")
            stages_run.append("stage3_topics")

            # Always use lightweight model for topic classification
            stage_model = get_lightweight_model()
            print(f"  Using model: {stage_model}")

            topic_result = classify_paper_topics(
                pdf_url, stage_model, api_key, paper_text=paper_text
            )
            topics = topic_result.get("topics", [])
            primary_topic = topic_result.get("primary_topic")
            print(f"  Topics: {topics}, Primary: {primary_topic}")

            if save_db:
                db.update_paper(
                    paper_id,
                    topics=", ".join(topics) if topics else None,
                    primary_topic=primary_topic,
                )
        else:
            topics_str = paper.get("topics", "")
            topics = topics_str.split(", ") if topics_str else []
            primary_topic = paper.get("primary_topic")
            print("\n========== Stage 3: Topic Classification (SKIPPED) ==========")
            print(f"  Using existing: {primary_topic}")

        # =================================================================
        # Stage 4: Summary Generation
        # =================================================================
        if run_summary and not use_abstract_fallback:
            print("\n========== Stage 4: Summary Generation ==========")
            stages_run.append("stage4_summary")

            prompt = load_prompt_template(topics=topics, primary_topic=primary_topic)

            if prompt_file:
                with open(prompt_file, "a") as f:
                    f.write(f"\n{'=' * 60}\nPaper ID: {paper_id}\n{'=' * 60}\n")
                    f.write(prompt)
                    f.write("\n")

            max_llm_retries = 3
            last_raw_response = None
            for llm_attempt in range(max_llm_retries):
                summary = generate_paper_summary(
                    pdf_url, prompt, model_name, api_key, paper_text=paper_text
                )

                if "raw_response" not in summary:
                    break

                last_raw_response = summary.get("raw_response", "")[:200]
                if llm_attempt < max_llm_retries - 1:
                    print(
                        f"  LLM returned invalid JSON, retrying... "
                        f"({llm_attempt + 1}/{max_llm_retries})"
                    )
            else:
                result["error"] = (
                    f"Could not parse summary JSON after {max_llm_retries} attempts. "
                    f"Last response: {last_raw_response}..."
                )
                return result

            result["summary"] = summary

            # Save summary to output directory
            if paper_output_dir:
                summary_path = paper_output_dir / "summary.json"
                with open(summary_path, "w") as f:
                    json.dump(summary, f, indent=2)
                print(f"  Summary saved to: {summary_path}")

            if save_db:
                db.update_paper_summary(paper_id, summary)
        elif use_abstract_fallback and run_summary:
            print("\n========== Stage 4: Summary Generation (SKIPPED) ==========")
            print("  Cannot generate summary from abstract alone")
            result["abstract_only"] = True
        else:
            print("\n========== Stage 4: Summary Generation (SKIPPED) ==========")
            print("  Summary already exists")

        result["success"] = True
        if use_abstract_fallback:
            result["abstract_only"] = True
        print(f"\nCompleted stages: {stages_run}")

    except Exception as e:
        result["error"] = str(e)
        print(f"  Error: {e}")
    finally:
        if should_close:
            db.close()

    return result


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Generate paper summaries using Google Gemini API"
    )
    parser.add_argument(
        "--pdf-url",
        type=str,
        help="URL to the paper PDF (e.g., https://arxiv.org/pdf/2501.15228)",
    )
    parser.add_argument(
        "--paper-id",
        type=int,
        help="Generate summary for a specific paper by database ID",
    )
    parser.add_argument(
        "--latest",
        type=int,
        help="Generate summaries for the latest N papers (by created_at)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate summaries for ALL papers in the database",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        help="Checkpoint file for resumable batch processing",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint file (requires --checkpoint)",
    )
    parser.add_argument(
        "--pdf-cache",
        type=str,
        help="Directory to cache downloaded PDFs (e.g., ./pdf_cache)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output directory to save all results (figures, summary JSON)",
    )
    parser.add_argument(
        "--prompt-file",
        type=str,
        help="Output file path for generated prompts (for debugging)",
    )
    parser.add_argument(
        "--save-db",
        action="store_true",
        help="Save topic and summary to database",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing summaries (default: skip existing)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Gemini model to use (default: from config.yaml)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="Google API key (or set GEMINI_API_KEY env var)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers for batch processing (default: 1)",
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=0,
        help="Max API requests per minute (0 = no limit, recommended: 10-30)",
    )

    args = parser.parse_args()

    # --resume with --checkpoint implies batch processing of remaining papers
    if args.resume and args.checkpoint:
        args.all = True

    # Check that at least one input source is specified
    if not any([args.all, args.latest, args.paper_id, args.pdf_url]):
        print("Error: No input specified. Provide one of the following:")
        print("  --all              Process ALL papers in the database")
        print("  --latest N         Process the latest N papers")
        print("  --paper-id ID      Process a specific paper by database ID")
        print("  --pdf-url URL      Process a single PDF from URL")
        print()
        print("For resuming from a checkpoint, use:")
        print("  --checkpoint FILE --resume")
        return

    # Process all papers or latest N papers
    if args.all or args.latest:
        import sys
        from concurrent.futures import as_completed, ThreadPoolExecutor

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from paper_db import PaperDB

        # Set up signal handlers for graceful shutdown
        setup_signal_handlers()

        # Initialize rate limiter
        if args.rate_limit > 0:
            print(f"Rate limiting enabled: {args.rate_limit} requests/minute")
            set_rate_limiter(RateLimiter(args.rate_limit))
        else:
            set_rate_limiter(RateLimiter(0))  # Disabled

        # Initialize checkpoint manager
        checkpoint = CheckpointManager(args.checkpoint)
        set_checkpoint_manager(checkpoint)

        # Initialize PDF cache
        if args.pdf_cache:
            print(f"PDF caching enabled: {args.pdf_cache}")
            set_pdf_cache(PDFCache(args.pdf_cache))
        else:
            set_pdf_cache(PDFCache(None))  # Disabled

        # Load existing checkpoint if resuming
        if args.resume:
            if not args.checkpoint:
                print("Error: --resume requires --checkpoint <file>")
                return
            if checkpoint.load():
                print(f"Resuming from checkpoint: {args.checkpoint}")
            else:
                print("No checkpoint found, starting fresh")

        db = PaperDB()
        papers = db.get_all_papers(order_by="created_at", order_dir="DESC")

        # Limit papers if --latest is specified, otherwise process all
        if args.latest:
            papers = papers[: args.latest]
            print(
                f"\nProcessing latest {len(papers)} papers (workers={args.workers})..."
            )
        else:
            print(f"\nProcessing ALL {len(papers)} papers (workers={args.workers})...")

        if not papers:
            print("No papers found in database")
            db.close()
            return

        # Get paper IDs
        all_paper_ids = [p["id"] for p in papers]
        paper_map = {p["id"]: p for p in papers}

        # Filter out already completed papers if resuming
        if args.resume and checkpoint.enabled:
            remaining_ids = checkpoint.get_remaining_ids(all_paper_ids)
            papers_to_process = [paper_map[pid] for pid in remaining_ids]
            skipped = len(papers) - len(papers_to_process)
            if skipped > 0:
                summary = checkpoint.get_summary()
                print(
                    f"Skipping {skipped} papers: "
                    f"{summary.get('completed', 0)} completed, "
                    f"{summary.get('permanent_errors', 0)} permanent errors"
                )
        else:
            papers_to_process = papers

        # Initialize checkpoint for this batch
        checkpoint.start_batch(len(papers), all_paper_ids)

        if args.checkpoint:
            print(f"Checkpoint file: {args.checkpoint}")
        print()

        all_results = []
        success_count = 0
        failed_count = 0

        def process_paper(paper):
            """Process a single paper (for parallel execution)."""
            paper_id = paper["id"]

            # Check for shutdown request
            if is_shutdown_requested():
                return {
                    "success": False,
                    "summary": None,
                    "error": "Shutdown requested",
                    "_paper_id": paper_id,
                    "_title": paper.get("title", ""),
                    "_skipped": True,
                }

            # Mark as in progress
            checkpoint.mark_in_progress(paper_id)

            try:
                result = generate_summary_for_paper(
                    paper_id=paper_id,
                    model_name=args.model,
                    api_key=args.api_key,
                    prompt_file=args.prompt_file,
                    save_db=args.save_db,
                    overwrite=args.overwrite,
                )
                # Add paper info for internal tracking
                result["_paper_id"] = paper_id
                result["_title"] = paper.get("title", "")

                # Update checkpoint
                if result["success"]:
                    if result.get("abstract_only"):
                        checkpoint.mark_abstract_only(
                            paper_id,
                            result.get("pdf_error"),
                        )
                    else:
                        checkpoint.mark_completed(paper_id)
                else:
                    checkpoint.mark_failed(paper_id, result.get("error"))

                return result

            except Exception as e:
                checkpoint.mark_failed(paper_id, str(e))
                return {
                    "success": False,
                    "summary": None,
                    "error": str(e),
                    "_paper_id": paper_id,
                    "_title": paper.get("title", ""),
                }

        if args.workers > 1:
            # Parallel processing with checkpointing
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = {
                    executor.submit(process_paper, p): p for p in papers_to_process
                }
                for future in as_completed(futures):
                    if is_shutdown_requested():
                        print("\n[!] Cancelling remaining tasks...")
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    result = future.result()
                    if not result.get("_skipped"):
                        all_results.append(result)
                        if result["success"]:
                            success_count += 1
                        else:
                            failed_count += 1
                    print("")
        else:
            # Sequential processing with checkpointing
            for i, paper in enumerate(papers_to_process, 1):
                if is_shutdown_requested():
                    print(f"\n[!] Stopped after {i - 1} papers")
                    break

                result = process_paper(paper)
                if not result.get("_skipped"):
                    all_results.append(result)
                    if result["success"]:
                        success_count += 1
                    else:
                        failed_count += 1
                print("")

        db.close()

        # Output results
        print("\n" + "=" * 60)
        print(
            f"BATCH PROCESSING {'INTERRUPTED' if is_shutdown_requested() else 'COMPLETE'}"
        )
        print("=" * 60)

        # Print checkpoint summary if enabled
        if checkpoint.enabled:
            summary = checkpoint.get_summary()
            print(
                f"Progress: {summary['completed']}/{summary['total']} completed, "
                f"{summary['failed']} failed, {summary['remaining']} remaining"
            )
            if is_shutdown_requested():
                print(
                    f"\nTo resume: python {sys.argv[0]} --latest {args.latest} "
                    f"--checkpoint {args.checkpoint} --resume"
                )
            # Print detailed error statistics
            checkpoint.print_stats()
        else:
            print(
                f"Processed: {success_count} success, {failed_count} failed (this session)"
            )

        if args.save_db:
            print("Database updated")

        if args.output and all_results:
            # Remove internal tracking fields before writing to JSON
            output_results = []
            for r in all_results:
                output_r = {k: v for k, v in r.items() if not k.startswith("_")}
                output_results.append(output_r)
            with open(args.output, "w") as f:
                json.dump(output_results, f, indent=2)
            print(f"Results saved to: {args.output}")
        elif not args.output and all_results:
            for r in all_results:
                status = "[OK]" if r["success"] else "[FAIL]"
                print(f"  {status} [{r['_paper_id']}] {r['_title'][:50]}...")
                if r.get("error"):
                    print(f"      Error: {r['error']}")
        return

    # Process a single paper by ID
    if args.paper_id:
        result = generate_summary_for_paper(
            paper_id=args.paper_id,
            model_name=args.model,
            api_key=args.api_key,
            prompt_file=args.prompt_file,
            output_dir=args.output,
            save_db=args.save_db,
            overwrite=args.overwrite,
        )
        if result["success"]:
            print("\nProcessing completed successfully!")
            if args.save_db:
                print("Database updated")
            if result.get("summary"):
                if args.output:
                    print(f"Summary: saved to {args.output}")
                else:
                    print("\n" + "=" * 60)
                    print("GENERATED SUMMARY")
                    print("=" * 60)
                    print(json.dumps(result["summary"], indent=2))
        else:
            print(f"\nError: {result['error']}")
        return

    # Generate summary if PDF URL provided
    if args.pdf_url:
        # Generate summary
        summary = generate_paper_summary(
            paper_url=args.pdf_url,
            prompt_template=None,
            model_name=args.model,
            api_key=args.api_key,
        )

        # Output result
        output_json = json.dumps(summary, indent=2)

        if args.output:
            with open(args.output, "w") as f:
                f.write(output_json)
            print(f"\nSummary saved to: {args.output}")
        else:
            print("\n" + "=" * 60)
            print("GENERATED SUMMARY")
            print("=" * 60)
            print(output_json)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
