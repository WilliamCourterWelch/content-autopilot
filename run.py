#!/usr/bin/env python3
"""
Run the podcast pipeline — one episode, a batch, or the GHL AI Studio lane.

Usage:
  python3 run.py                    # one episode from your content source
  python3 run.py --batch            # full batch (up to daily limit)
  python3 run.py --topic "Topic"    # one episode on a specific topic
  python3 run.py --limit 5          # batch of 5 episodes
  python3 run.py --ai-lane          # one GHL AI help topic → Studio audio
  python3 run.py --ai-lane --formats audio,report,infographic --limit 1
  python3 run.py --ai-lane --url https://help.gohighlevel.com/... --dry-run
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PUBLISHED_FILE = DATA_DIR / "published.json"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)


def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"  [{timestamp}] {msg}")


def load_published():
    if PUBLISHED_FILE.exists():
        return json.loads(PUBLISHED_FILE.read_text())
    return []


def save_published(records):
    PUBLISHED_FILE.write_text(json.dumps(records, indent=2))


def get_content(topic=None):
    """Get content from the configured source(s)."""
    source_types = os.getenv("CONTENT_SOURCE_TYPES", "manual").split(",")

    if topic:
        # Manual topic override — use the manual scraper
        from scripts.scrapers.manual import research_topic
        return research_topic(topic)

    # Try each configured source in order
    for source_type in source_types:
        source_type = source_type.strip()

        if source_type == "website":
            from scripts.scrapers.web import get_next_article
            content = get_next_article()
            if content:
                return content

        elif source_type == "youtube":
            from scripts.scrapers.youtube import get_next_video
            content = get_next_video()
            if content:
                return content

        elif source_type == "rss":
            from scripts.scrapers.rss import get_next_item
            content = get_next_item()
            if content:
                return content

        elif source_type == "manual":
            from scripts.scrapers.manual import get_next_topic
            content = get_next_topic()
            if content:
                return content

    # Fallback: auto-discover new topics if all sources are exhausted
    from scripts.scrapers.discover import get_next_discovered
    content = get_next_discovered()
    if content:
        return content

    return None


def run_episode(topic=None):
    """Run the full pipeline for one episode."""
    # Step 1: Get content
    log("Getting content...")
    content = get_content(topic=topic)
    if not content:
        log("No content available. Add topics to data/topics.json or check your content source.")
        return False

    log(f"Content: {content.get('title', 'Untitled')}")

    # Step 2: Generate audio with NotebookLM
    log("Generating podcast audio (this takes a few minutes)...")
    try:
        from scripts.notebooklm import generate_audio
        audio_result = generate_audio(content)
        if not audio_result:
            log("Audio generation failed.")
            return False
        log("Audio generated.")
    except Exception as e:
        log(f"Audio generation error: {e}")
        return False

    # Step 3: SEO metadata
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    seo_data = {}
    if anthropic_key:
        log("Writing SEO metadata...")
        try:
            from scripts.seo import write_seo
            seo_data = write_seo(content, os.getenv("PODCAST_NICHE", ""))
            log(f"SEO title: {seo_data.get('title', 'N/A')}")
        except Exception as e:
            log(f"SEO error (non-fatal): {e}")
    else:
        log("Skipping SEO — no ANTHROPIC_API_KEY configured.")
        seo_data = {
            "title": content.get("title", "Untitled Episode"),
            "description": content.get("summary", ""),
            "tags": [],
        }

    # Step 4: Transcribe
    transcript = ""
    if os.getenv("ENABLE_TRANSCRIPTION", "false").lower() == "true" and os.getenv("GOOGLE_AI_API_KEY"):
        log("Transcribing audio...")
        try:
            from scripts.transcribe import transcribe_audio
            transcript = transcribe_audio(audio_result["audio_path"])
            log("Transcription complete.")
        except Exception as e:
            log(f"Transcription error (non-fatal): {e}")

    # Step 5: Upload to Transistor
    transistor_key = os.getenv("TRANSISTOR_API_KEY")
    show_id = os.getenv("TRANSISTOR_SHOW_ID")
    episode_data = {}

    if transistor_key and show_id:
        log("Uploading to Transistor.fm...")
        try:
            from scripts.upload import upload_episode
            episode_data = upload_episode(
                audio_path=audio_result["audio_path"],
                title=seo_data.get("title", content["title"]),
                description=seo_data.get("description", ""),
                tags=seo_data.get("tags", []),
                transcript=transcript,
            )
            log(f"Published: {episode_data.get('share_url', 'done')}")
        except Exception as e:
            log(f"Upload error: {e}")
            return False
    else:
        log("Skipping upload — Transistor not configured. Audio saved locally.")

    # Step 6: Blog post (optional)
    if os.getenv("ENABLE_BLOG", "false").lower() == "true" and anthropic_key:
        log("Writing blog post...")
        try:
            from scripts.blog import write_blog_post
            blog_result = write_blog_post(
                content=content,
                seo_data=seo_data,
                episode_data=episode_data,
            )
            log(f"Blog post: {blog_result.get('slug', 'done')}")
        except Exception as e:
            log(f"Blog error (non-fatal): {e}")

    # Save to published.json
    published = load_published()
    published.append({
        "title": seo_data.get("title", content.get("title", "")),
        "source": content.get("source_url", ""),
        "source_type": content.get("source_type", ""),
        "audio_path": audio_result.get("audio_path", ""),
        "transistor_id": episode_data.get("id", ""),
        "status": "published" if episode_data.get("id") else "local",
        "published_at": datetime.now().isoformat(),
    })
    save_published(published)

    log("Done.")
    return True


def build_parser():
    parser = argparse.ArgumentParser(description="Run the podcast pipeline or GHL AI Studio lane")
    parser.add_argument("--topic", help="Generate an episode on this specific topic")
    parser.add_argument("--batch", action="store_true", help="Run a full batch")
    parser.add_argument("--limit", type=int, help="Max episodes / AI-lane topics (default 1 for --ai-lane)")
    parser.add_argument(
        "--ai-lane",
        action="store_true",
        help="GHL AI multi-format Studio lane (Conversation AI / Voice AI / agents)",
    )
    parser.add_argument(
        "--formats",
        help="Studio types for --ai-lane (comma list or 'all'). Default: audio",
    )
    parser.add_argument(
        "--url",
        help="Single help.gohighlevel.com (or changelog) URL for --ai-lane",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="AI lane: filter + format parse only (no NotebookLM, no publish)",
    )
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="AI lane: generate and save under data/, skip publishers",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="AI lane: allow --limit above the canary cap of 3",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    needs_env = not (args.ai_lane and (args.dry_run or args.no_publish))
    if needs_env and not args.dry_run and not Path(BASE_DIR / ".env").exists():
        if not args.ai_lane:
            print("\n  No .env file found. Run setup.py first:\n")
            print("    python3 setup.py\n")
            sys.exit(1)

    if args.ai_lane:
        from scripts.ai_lane import run_ai_lane

        try:
            result = run_ai_lane(
                formats=args.formats,
                url=args.url,
                limit=args.limit or 1,
                dry_run=args.dry_run,
                no_publish=args.no_publish,
                force=args.force,
            )
        except ValueError as e:
            print(f"\n  AI lane rejected source: {e}\n")
            sys.exit(2)
        if not result.get("ok"):
            sys.exit(2)
        return

    print()
    print("  Podcast Pipeline")
    print("  ─────────────────")
    print()

    if not Path(BASE_DIR / ".env").exists():
        print("  No .env file found. Run setup.py first:\n")
        print("    python3 setup.py\n")
        sys.exit(1)

    if args.topic:
        run_episode(topic=args.topic)
    elif args.batch:
        limit = args.limit or int(os.getenv("EPISODES_PER_DAY", "3"))
        log(f"Running batch of {limit} episodes...")
        print()
        successes = 0
        for i in range(limit):
            log(f"── Episode {i + 1}/{limit} ──")
            if run_episode():
                successes += 1
            print()
        log(f"Batch complete: {successes}/{limit} episodes published.")
    else:
        run_episode(topic=args.topic)

    print()


if __name__ == "__main__":
    main()
