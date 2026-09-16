"""
GHL AI multi-format Studio lane.

Given a help.gohighlevel.com (or changelog) URL about Conversation AI /
Voice AI / agents, generate selectable NotebookLM Studio artifacts and
hand them to pluggable publishers. Default is one topic — no volume blast.

HARD: do not create thin new HTML pages on globalhighlevel.com.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scripts.formats import DEFAULT_AI_LANE_FORMATS, parse_formats
from scripts.publishers import publish_artifacts
from scripts.source_filter import classify_ghl_ai_source, filter_sources, is_thin_site_destination

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
PUBLISHED_FILE = DATA_DIR / "published.json"

# Ready AI-lane candidates from the 2026-09-16 canary report.
SEED_AI_URLS = (
    "https://help.gohighlevel.com/support/solutions/articles/155000004401-how-to-set-up-a-conversation-ai-bot",
    "https://help.gohighlevel.com/support/solutions/articles/155000007796-voice-ai-agent-transfer",
    "https://help.gohighlevel.com/support/solutions/articles/155000005427-conversation-ai-agents-dashboard",
)

HELP_SEARCH = "https://help.gohighlevel.com/support/search/solutions?term={term}"
SEARCH_TERMS = (
    "Conversation AI",
    "Voice AI",
    "AI agent",
    "AI employee",
)

# Hard cap so `--limit 50` cannot spray. Override only with --force.
MAX_TOPICS_WITHOUT_FORCE = 3

USER_AGENT = "ContentAutopilot-GHL-AI-Lane/1.0"


def log(msg):
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_published():
    if PUBLISHED_FILE.exists():
        return json.loads(PUBLISHED_FILE.read_text(encoding="utf-8"))
    return []


def save_published(records):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISHED_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")


def published_urls():
    return {r.get("source", "") for r in load_published() if r.get("source")}


def scrape_article(url: str) -> dict | None:
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except requests.RequestException:
        return None

    # Re-check the final URL so a help.gohighlevel.com redirect cannot leave the allowlist.
    final_url = resp.url or url
    if not classify_ghl_ai_source(final_url, require_ai=False).accepted:
        return None
    url = final_url

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup.find_all(["nav", "footer", "aside", "script", "style", "header"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"}) or soup.find("body")
    if not main:
        return None
    title = ""
    if soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)
    elif soup.find("title"):
        title = soup.find("title").get_text(strip=True)
    body = main.get_text(separator="\n", strip=True)
    if len(body) < 80:
        return None
    return {
        "title": title or "GHL AI article",
        "body": body,
        "source_url": url,
        "source_type": "ghl-ai-help",
    }


def _discover_search_urls(limit: int) -> list[str]:
    found = []
    seen = set()
    for term in SEARCH_TERMS:
        if len(found) >= limit * 4:
            break
        url = HELP_SEARCH.format(term=quote_plus(term))
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
        except requests.RequestException:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"]).split("#")[0]
            path = urlparse(href).path or ""
            if "/support/solutions/articles/" not in path:
                continue
            if href in seen:
                continue
            seen.add(href)
            found.append(href)
    return found


def discover_ai_sources(limit: int = 1, extra_urls=None) -> list[dict]:
    """Find GHL AI help/changelog URLs, filter, scrape. Seeds if search is empty."""
    candidates = []
    if extra_urls:
        candidates.extend(extra_urls)
    candidates.extend(SEED_AI_URLS)
    try:
        candidates.extend(_discover_search_urls(limit))
    except Exception:
        pass

    # Dedup, skip already published, apply AI allowlist
    already = published_urls()
    unique = []
    seen = set()
    for url in candidates:
        if not url or url in seen or url in already:
            continue
        seen.add(url)
        unique.append({"source_url": url, "url": url})

    accepted = filter_sources(unique, require_ai=True)
    contents = []
    for item in accepted:
        url = item.get("source_url") or item.get("url")
        page = scrape_article(url)
        if not page:
            # URL + slug still passed the filter — keep a thin body so dry-run works.
            page = {
                "title": url.rsplit("/", 1)[-1].replace("-", " "),
                "body": item.get("_ai_filter", {}).get("reason", "GHL AI help article"),
                "source_url": url,
                "source_type": "ghl-ai-help",
            }
        verdict = classify_ghl_ai_source(page["source_url"], page.get("title", ""), page.get("body", ""))
        if not verdict.accepted:
            continue
        page["_ai_filter"] = {
            "reason": verdict.reason,
            "matched": list(verdict.matched),
            "kind": verdict.kind,
        }
        contents.append(page)
        if len(contents) >= limit:
            break
    return contents


def resolve_topics(url=None, limit=1, force=False) -> list[dict]:
    limit = int(limit or 1)
    if limit < 1:
        limit = 1
    if not force and limit > MAX_TOPICS_WITHOUT_FORCE:
        log(f"Capping --limit {limit} to {MAX_TOPICS_WITHOUT_FORCE} (pass --force to override).")
        limit = MAX_TOPICS_WITHOUT_FORCE

    if url:
        if is_thin_site_destination(url):
            raise ValueError("HARD: no thin new HTML pages on globalhighlevel.com")
        page = scrape_article(url) or {
            "title": url.rsplit("/", 1)[-1].replace("-", " "),
            "body": "",
            "source_url": url,
            "source_type": "ghl-ai-help",
        }
        verdict = classify_ghl_ai_source(page["source_url"], page.get("title", ""), page.get("body", ""))
        if not verdict.accepted:
            raise ValueError(f"Source rejected: {verdict.reason}")
        page["_ai_filter"] = {
            "reason": verdict.reason,
            "matched": list(verdict.matched),
            "kind": verdict.kind,
        }
        return [page]

    return discover_ai_sources(limit=limit)


def run_ai_lane(
    formats=None,
    url=None,
    limit=1,
    dry_run=False,
    no_publish=False,
    force=False,
    skip_blog=True,
):
    """
    One-topic-by-default GHL AI Studio run.

    dry_run: filter + format parse only (no NotebookLM, no publish).
    no_publish: generate + download to data/, skip publishers.
    skip_blog: always True for this lane — anti-thin-site rule.
    """
    if os.getenv("SITE_URL") and is_thin_site_destination(os.getenv("SITE_URL")):
        log("SITE_URL points at globalhighlevel.com — refusing HTML publish (anti-thin-site).")

    requested = parse_formats(formats or os.getenv("AI_LANE_FORMATS") or DEFAULT_AI_LANE_FORMATS)
    topics = resolve_topics(url=url, limit=limit, force=force)

    print()
    print("  GHL AI Studio lane")
    print("  ──────────────────")
    print(f"  formats: {', '.join(requested)}")
    print(f"  topics:  {len(topics)} (default canary is 1)")
    print("  rule:    no thin new HTML on globalhighlevel.com")
    print()

    if not topics:
        log("No GHL AI sources passed the allowlist.")
        return {"ok": False, "topics": [], "results": []}

    results = []
    for content in topics:
        filt = content.get("_ai_filter") or {}
        log(f"Source: {content.get('title')}")
        log(f"  url: {content.get('source_url')}")
        log(f"  filter: {filt.get('reason', 'ok')}")

        if dry_run:
            results.append(
                {
                    "title": content.get("title"),
                    "source_url": content.get("source_url"),
                    "formats": requested,
                    "status": "dry-run",
                    "filter": filt,
                }
            )
            continue

        from scripts.notebooklm import generate_studio

        log(f"Generating Studio artifacts via notebooklm generate ({', '.join(requested)})...")
        studio = generate_studio(content, requested)
        artifacts = studio.get("artifacts") or []
        for art in artifacts:
            log(f"  saved {art['format']}: {art['path']}")

        seo_data = {
            "title": content.get("title"),
            "description": (content.get("body") or "")[:240],
            "tags": list((filt.get("matched") or [])[:8]),
        }
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            try:
                from scripts.seo import write_seo

                seo_data = write_seo(content, os.getenv("PODCAST_NICHE", "GoHighLevel AI"))
            except Exception as e:
                log(f"SEO error (non-fatal): {e}")

        publishes = []
        if no_publish:
            log("Skipping publish (--no-publish). Artifacts stay in data/.")
        else:
            publishes = publish_artifacts(artifacts, content, seo_data=seo_data)
            for pub in publishes:
                log(f"  {pub.get('channel')}: {pub.get('status')} — {pub.get('reason')}")

        if skip_blog:
            log("Skipping blog/HTML site build (anti-thin-site rule).")

        record = {
            "title": seo_data.get("title", content.get("title", "")),
            "source": content.get("source_url", ""),
            "source_type": "ghl-ai-studio",
            "formats": [a.get("format") for a in artifacts],
            "artifacts": artifacts,
            "publish": publishes,
            "status": "published" if any(p.get("status") == "published" for p in publishes) else "local",
            "published_at": datetime.now().isoformat(),
        }
        published = load_published()
        published.append(record)
        save_published(published)
        results.append(record)

    return {"ok": True, "topics": topics, "results": results, "formats": requested}
