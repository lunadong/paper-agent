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
import io
import json
import os
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: requests package not installed.")
    print("Install it with: pip install requests")
    exit(1)

try:
    import yaml
except ImportError:
    yaml = None

# Try to import PDF parsing libraries
try:
    import PyPDF2

    PDF_SUPPORT = True
except ImportError:
    PyPDF2 = None
    PDF_SUPPORT = False


# API configuration
DEFAULT_API_URL = "https://api.wearables-ape.io/conversations/sync"
DEFAULT_MODEL = "gemini-2.0-flash"
MAX_PDF_CHARS = 100000  # Limit PDF text to avoid token limits


def download_pdf_text(pdf_url: str, max_chars: int = MAX_PDF_CHARS) -> str:
    """
    Download a PDF from URL and extract its text content.

    Args:
        pdf_url: URL to the PDF file.
        max_chars: Maximum characters to extract (to avoid token limits).

    Returns:
        Extracted text from the PDF.
    """
    if not PDF_SUPPORT:
        raise ImportError(
            "PyPDF2 is required for PDF extraction.\n"
            "Install it with: pip install PyPDF2"
        )

    print(f"Downloading PDF from: {pdf_url}")

    # Download the PDF
    response = requests.get(pdf_url, timeout=60)
    if response.status_code != 200:
        raise Exception(f"Failed to download PDF: HTTP {response.status_code}")

    # Parse the PDF
    pdf_file = io.BytesIO(response.content)
    pdf_reader = PyPDF2.PdfReader(pdf_file)

    # Extract text from all pages
    text_parts = []
    total_chars = 0

    for page_num, page in enumerate(pdf_reader.pages):
        page_text = page.extract_text()
        if page_text:
            text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")
            total_chars += len(page_text)

            if total_chars >= max_chars:
                print(f"  Reached {max_chars} char limit at page {page_num + 1}")
                break

    full_text = "\n\n".join(text_parts)
    print(f"  Extracted {len(full_text)} characters from {len(text_parts)} pages")

    return full_text[:max_chars]


def load_config() -> dict:
    """
    Load configuration from config.yaml.

    Returns:
        Configuration dictionary with gemini settings.
    """
    config_paths = [
        Path(__file__).parent.parent / "config.yaml",
        Path.cwd() / "config.yaml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            if yaml is None:
                print("Warning: PyYAML not installed. Using default config.")
                break
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
                return config.get("gemini", {})

    return {}


def get_config_value(key: str, default: str = None) -> str:
    """
    Get a value from config, environment, or default.

    Args:
        key: Config key (e.g., 'api_key', 'api_url', 'model')
        default: Default value if not found

    Returns:
        Config value string.
    """
    config = load_config()
    env_key = f"GEMINI_{key.upper()}"
    return os.environ.get(env_key, config.get(key, default))


def get_api_key(api_key: str = None) -> str:
    """
    Get the API key from parameter, environment, or config file.

    Args:
        api_key: API key. If None, reads from GEMINI_API_KEY env var or config.yaml.

    Returns:
        API key string.
    """
    if api_key is None:
        api_key = get_config_value("api_key", "")

    if not api_key:
        raise ValueError(
            "API key not found. Set it in config.yaml, GEMINI_API_KEY env var, "
            "or pass it directly."
        )

    return api_key


def get_api_url() -> str:
    """Get the API URL from config or default."""
    return get_config_value("api_url", DEFAULT_API_URL)


def get_default_model() -> str:
    """Get the default model from config or default."""
    return get_config_value("model", DEFAULT_MODEL)


def call_gemini_api(
    prompt: str,
    model_name: str = None,
    api_key: str = None,
) -> str:
    """
    Call the Gemini API via wearables-ape.io.

    Args:
        prompt: The prompt to send to the model.
        model_name: Model to use (default: from config or gemini-2.0-flash)
        api_key: API key. If None, uses default.

    Returns:
        Response text from the model.
    """
    api_key = get_api_key(api_key)
    if model_name is None:
        model_name = get_default_model()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "accept": "application/json",
    }

    payload = {
        "name": "llm-text-gen",
        "outputVariableName": "last_output",
        "model_api_name": model_name,
        "stream": False,
        "user": prompt,
    }

    api_url = get_api_url()
    response = requests.post(api_url, headers=headers, json=payload, timeout=120)

    if response.status_code != 200:
        raise Exception(
            f"API Error: {response.status_code}\n{response.text}\n"
            f"Request body:\n{json.dumps(payload, indent=2)}"
        )

    result = response.json()

    # Extract the response text from the API response
    if "result" in result:
        return result["result"]
    elif "choices" in result and len(result["choices"]) > 0:
        return result["choices"][0].get("message", {}).get("content", "")
    elif "content" in result:
        return result["content"]
    elif "response" in result:
        return result["response"]
    else:
        # Return the raw response if we can't parse it
        return json.dumps(result)


def load_prompt_template(prompt_file: str = None) -> str:
    """
    Load the prompt template from file and populate placeholders.

    Replaces:
        - <json_template> with contents of summary_template.json
        - <json_example> with contents of summary_example.json

    Args:
        prompt_file: Path to prompt file. Defaults to prompt.txt in same directory.

    Returns:
        Prompt template string with placeholders replaced.
    """
    if prompt_file is None:
        script_dir = Path(__file__).parent
        prompt_file = script_dir / "prompt.txt"
    else:
        script_dir = Path(prompt_file).parent

    with open(prompt_file, "r") as f:
        prompt = f.read()

    # Load and replace <json_template>
    template_file = script_dir / "summary_template.json"
    if template_file.exists():
        with open(template_file, "r") as f:
            json_template = f.read()
        prompt = prompt.replace("<json_template>", json_template)

    # Load and replace <json_example>
    example_file = script_dir / "summary_example.json"
    if example_file.exists():
        with open(example_file, "r") as f:
            json_example = f.read()
        prompt = prompt.replace("<json_example>", json_example)

    return prompt


def load_json_template(template_file: str = None) -> dict:
    """
    Load the JSON template from file.

    Args:
        template_file: Path to template file. Defaults to summary_template.json.

    Returns:
        JSON template as dictionary.
    """
    if template_file is None:
        script_dir = Path(__file__).parent
        template_file = script_dir / "summary_template.json"

    with open(template_file, "r") as f:
        return json.load(f)


def generate_paper_summary(
    pdf_url: str,
    prompt_template: str = None,
    model_name: str = None,
    api_key: str = None,
) -> dict:
    """
    Generate a structured summary for a paper given its PDF URL.

    Downloads the PDF, extracts text, and includes it in the prompt
    so the model can read the actual paper content.

    Args:
        pdf_url: URL to the paper PDF (e.g., arXiv PDF link)
        prompt_template: Custom prompt template. If None, loads from prompt.txt
        model_name: Gemini model to use (default: from config)
        api_key: API key. If None, uses default.

    Returns:
        Parsed JSON summary dictionary.
    """
    if model_name is None:
        model_name = get_default_model()

    # Load prompt template if not provided
    if prompt_template is None:
        prompt_template = load_prompt_template()

    # Download and extract PDF text
    print(f"Generating summary for: {pdf_url}")
    pdf_text = download_pdf_text(pdf_url)

    # Build the prompt with actual PDF content
    prompt = prompt_template.replace("<PDF_URL>", pdf_url)

    # Insert the PDF content after the URL line
    pdf_content_section = f"\n\n========================\nPaper Content (extracted from PDF)\n========================\n\n{pdf_text}\n"
    prompt = prompt.replace(
        "For the above paper in the given link,",
        f"{pdf_content_section}\nFor the above paper content,",
    )

    print(f"Using model: {model_name}")
    print(f"Prompt length: {len(prompt)} characters")

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
            print("Warning: Could not find JSON in response")
            return {"raw_response": response_text}

    except json.JSONDecodeError as e:
        print(f"Warning: Could not parse JSON: {e}")
        return {"raw_response": response_text}


def generate_text(
    prompt: str,
    model_name: str = DEFAULT_MODEL,
    api_key: str = None,
) -> str:
    """
    Generate text using the Gemini API.

    Args:
        prompt: The prompt to send to the model.
        model_name: Gemini model to use (default: gemini-2.0-flash)
        api_key: API key. If None, uses default.

    Returns:
        Generated text response.
    """
    return call_gemini_api(prompt, model_name, api_key)


def list_models():
    """
    List available Gemini models.
    """
    print("Available models (via wearables-ape.io):")
    print("  - gemini-2.0-flash (default)")
    print("  - gemini-1.5-flash")
    print("  - gemini-1.5-pro")
    print("  - gemini-1.0-pro")


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
        "--prompt",
        type=str,
        help="Custom prompt text (overrides prompt.txt)",
    )
    parser.add_argument(
        "--prompt-file",
        type=str,
        help="Path to custom prompt file",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Gemini model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="Google API key (or set GEMINI_API_KEY env var)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path for JSON summary",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available Gemini models",
    )
    parser.add_argument(
        "--paper-id",
        type=int,
        help="Generate summary for a specific paper by database ID",
    )
    parser.add_argument(
        "--process-rag-papers",
        action="store_true",
        help="Process all papers with RAG tag that don't have summaries yet",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of papers to process (for --process-rag-papers)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers for batch processing (default: 1)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing summaries (default: skip papers with existing summaries)",
    )

    args = parser.parse_args()

    # List models if requested
    if args.list_models:
        list_models()
        return

    # Process all RAG papers
    if args.process_rag_papers:
        process_rag_papers(
            model_name=args.model,
            api_key=args.api_key,
            limit=args.limit,
            workers=args.workers,
            overwrite=args.overwrite,
        )
        return

    # Process a single paper by ID
    if args.paper_id:
        result = generate_summary_for_paper(
            paper_id=args.paper_id,
            model_name=args.model,
            api_key=args.api_key,
        )
        if result["success"]:
            print("\nSummary generated successfully!")
            if args.output:
                with open(args.output, "w") as f:
                    json.dump(result["summary"], f, indent=2)
                print(f"Summary saved to: {args.output}")
            else:
                print(json.dumps(result["summary"], indent=2))
        else:
            print(f"\nError: {result['error']}")
        return

    # Generate summary if PDF URL provided
    if args.pdf_url:
        # Load prompt
        if args.prompt:
            prompt_template = args.prompt
        elif args.prompt_file:
            with open(args.prompt_file, "r") as f:
                prompt_template = f.read()
        else:
            prompt_template = None

        # Generate summary
        summary = generate_paper_summary(
            pdf_url=args.pdf_url,
            prompt_template=prompt_template,
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
        print("\nExample usage:")
        print(
            '  python summary_generation.py --pdf-url "https://arxiv.org/pdf/2501.15228"'
        )
        print(
            '  python summary_generation.py --pdf-url "https://arxiv.org/pdf/2501.15228" --model "gemini-1.5-pro"'
        )
        print(
            '  python summary_generation.py --pdf-url "https://arxiv.org/pdf/2501.15228" --output summary.json'
        )
        print("  python summary_generation.py --list-models")
        print("  python summary_generation.py --process-rag-papers")


def get_rag_papers_needing_summary(
    db=None,
    overwrite: bool = False,
) -> list[dict]:
    """
    Get all papers with RAG topic that don't have summaries yet.

    Args:
        db_path: Path to the papers database
        db: Optional PaperDB instance to reuse (for efficiency in batch operations)
        overwrite: If True, return all RAG papers regardless of existing summaries

    Returns:
        List of paper dictionaries needing summaries
    """
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from paper_db import PaperDB

    # Use provided db or create new one
    should_close = db is None
    if db is None:
        db = PaperDB()

    # Get papers with RAG topic
    rag_papers = db.get_papers_by_topic("RAG")

    # Filter based on overwrite flag
    if overwrite:
        papers_to_process = rag_papers
    else:
        papers_to_process = [p for p in rag_papers if not p.get("summary_generated_at")]

    if should_close:
        db.close()

    return papers_to_process


def generate_summary_for_paper(
    paper_id: int,
    model_name: str = None,
    api_key: str = None,
    db=None,
) -> dict:
    """
    Generate and store summary for a single paper by its database ID.

    This function:
    1. Looks up the paper in the database
    2. Downloads the PDF and generates a summary using LLM
    3. Stores the summary in the database
    4. If is_about_rag is False, removes the 'rag' tag

    Args:
        paper_id: The paper's database ID
        db_path: Path to the papers database
        model_name: Gemini model to use (default: from config)
        api_key: API key (default: from config)
        db: Optional PaperDB instance to reuse (for efficiency in batch operations)

    Returns:
        Dictionary with:
        - success: bool - Whether summary was generated successfully
        - summary: dict - The generated summary (if successful)
        - rag_removed: bool - Whether the 'rag' tag was removed
        - error: str - Error message (if failed)
    """
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from paper_db import PaperDB

    if model_name is None:
        model_name = get_default_model()

    result = {
        "success": False,
        "summary": None,
        "rag_removed": False,
        "error": None,
    }

    # Use provided db or create new one
    should_close = db is None
    if db is None:
        db = PaperDB()

    # Get paper by ID
    paper = db.get_paper_by_id(paper_id)
    if not paper:
        if should_close:
            db.close()
        result["error"] = f"Paper with ID {paper_id} not found"
        return result

    title = paper["title"]
    link = paper.get("link", "")

    print(f"Processing paper ID {paper_id}: {title[:60]}...")
    print(f"  Link: {link}")

    # Get PDF URL (try to convert arXiv abs URL to PDF URL)
    pdf_url = link
    if "arxiv.org/abs/" in link:
        pdf_url = link.replace("/abs/", "/pdf/")
        if not pdf_url.endswith(".pdf"):
            pdf_url += ".pdf"

    if not pdf_url or "arxiv.org" not in pdf_url:
        if should_close:
            db.close()
        result["error"] = "No valid arXiv PDF URL"
        print(f"  Error: {result['error']}")
        return result

    try:
        # Generate summary
        summary = generate_paper_summary(
            pdf_url=pdf_url,
            model_name=model_name,
            api_key=api_key,
        )

        # Check if we got a valid summary
        if "raw_response" in summary:
            if should_close:
                db.close()
            result["error"] = "Could not parse JSON response from LLM"
            print(f"  Error: {result['error']}")
            return result

        # Store summary in database
        db.update_paper_summary(paper_id, summary)
        print("  Summary stored in database")

        result["success"] = True
        result["summary"] = summary

        # Check is_about_rag and remove tag if False
        is_about_rag = (
            summary.get("Core", {}).get("rag_relevance", {}).get("is_about_rag", True)
        )

        if not is_about_rag:
            db.remove_tag(paper_id, "rag")
            result["rag_removed"] = True
            print("  Removed 'rag' tag (is_about_rag=False)")

    except Exception as e:
        result["error"] = str(e)
        print(f"  Error: {result['error']}")

    if should_close:
        db.close()
    return result


def process_rag_papers(
    model_name: str = None,
    api_key: str = None,
    limit: int = None,
    workers: int = 1,
    overwrite: bool = False,
) -> dict:
    """
    Process all papers with RAG tag and store summaries to database.

    This is a convenience function that combines get_rag_papers_needing_summary()
    and generate_summary_for_paper() to batch process multiple papers.

    Args:
        db_path: Path to the papers database
        model_name: Gemini model to use
        api_key: API key
        limit: Maximum number of papers to process
        workers: Number of parallel workers (default: 1 for sequential)
        overwrite: If True, regenerate summaries even if they already exist

    Returns:
        Summary of processing results
    """
    import sys
    from concurrent.futures import as_completed, ThreadPoolExecutor

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from paper_db import PaperDB

    # Get papers needing summaries
    db = PaperDB()
    papers_to_process = get_rag_papers_needing_summary(db=db, overwrite=overwrite)
    db.close()

    if limit:
        papers_to_process = papers_to_process[:limit]

    mode_str = (
        "ALL RAG papers (overwrite mode)"
        if overwrite
        else "RAG papers needing summaries"
    )
    print(f"Found {len(papers_to_process)} {mode_str}")
    print(f"Using {workers} parallel worker(s)")

    if not papers_to_process:
        print("No papers to process!")
        return {"processed": 0, "success": 0, "failed": 0, "rag_removed": 0}

    results = {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "rag_removed": 0,
        "errors": [],
    }

    def process_single_paper(paper_info):
        """Worker function to process a single paper."""
        idx, paper = paper_info
        paper_id = paper["id"]
        title = paper["title"]

        print(f"\n[{idx + 1}/{len(papers_to_process)}] Processing: {title[:50]}...")

        # Each worker gets its own DB connection
        result = generate_summary_for_paper(
            paper_id=paper_id,
            model_name=model_name,
            api_key=api_key,
            db=None,  # Let it create its own connection
        )

        return {
            "paper_id": paper_id,
            "title": title,
            "result": result,
        }

    # Process papers in parallel
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(process_single_paper, (i, paper)): paper
                for i, paper in enumerate(papers_to_process)
            }

            for future in as_completed(futures):
                try:
                    output = future.result()
                    results["processed"] += 1

                    if output["result"]["success"]:
                        results["success"] += 1
                        if output["result"]["rag_removed"]:
                            results["rag_removed"] += 1
                        print(f"  ✓ {output['title'][:40]}... SUCCESS")
                    else:
                        results["failed"] += 1
                        results["errors"].append(
                            {
                                "id": output["paper_id"],
                                "title": output["title"],
                                "error": output["result"]["error"],
                            }
                        )
                        print(f"  ✗ {output['title'][:40]}... FAILED")
                except Exception as e:
                    results["failed"] += 1
                    print(f"  ✗ Worker exception: {str(e)}")
    else:
        # Sequential processing (original behavior)
        db = PaperDB()
        for i, paper in enumerate(papers_to_process):
            paper_id = paper["id"]
            title = paper["title"]

            print(f"\n{'=' * 60}")
            print(f"[{i + 1}/{len(papers_to_process)}] Processing: {title[:60]}...")

            result = generate_summary_for_paper(
                paper_id=paper_id,
                model_name=model_name,
                api_key=api_key,
                db=db,
            )

            results["processed"] += 1

            if result["success"]:
                results["success"] += 1
                if result["rag_removed"]:
                    results["rag_removed"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(
                    {"id": paper_id, "title": title, "error": result["error"]}
                )
        db.close()

    print(f"\n{'=' * 60}")
    print("PROCESSING COMPLETE")
    print("=" * 60)
    print(f"  Total processed: {results['processed']}")
    print(f"  Successful: {results['success']}")
    print(f"  Failed: {results['failed']}")
    print(f"  RAG tags removed: {results['rag_removed']}")

    return results


if __name__ == "__main__":
    main()
