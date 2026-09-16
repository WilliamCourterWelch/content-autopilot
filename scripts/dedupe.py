"""
Dedupe gate — never generate or publish a topic we already did.

Checks, in order:
  1. data/known-episodes.json (committed fingerprints, including the 2026-09-16
     whitelabel canary)
  2. data/published.json (source_url + normalized title)
  3. Transistor show episodes (title / source fingerprint) when API keys exist
  4. Optional: existing globalhighlevel.com slugs / pillar pages

A hit skips generate + publish. --force does not bypass this gate.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
KNOWN_FILE = DATA_DIR / "known-episodes.json"
PUBLISHED_FILE = DATA_DIR / "published.json"
PILLAR_FILE = DATA_DIR / "pillar-pages.json"

HELP_ARTICLE_ID = re.compile(r"/articles/(\d+)")
NON_ALNUM = re.compile(r"[^a-z0-9\s]+")
WS = re.compile(r"\s+")
HOW_TO = re.compile(r"^(how\s+to\s+|complete\s+guide\s+to\s+)")

USER_AGENT = "ContentAutopilot-Dedupe/1.0"


@dataclass(frozen=True)
class DedupeHit:
    duplicate: bool
    reason: str
    source: str = ""  # known | published | transistor | ghl-site
    matched: str = ""


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower().removeprefix("www.")
    path = (parsed.path or "").rstrip("/").lower()
    return urlunparse(("https", host, path, "", "", ""))


def article_id(url: str) -> str:
    match = HELP_ARTICLE_ID.search(url or "")
    return match.group(1) if match else ""


def normalize_title(title: str) -> str:
    text = (title or "").lower().replace("&", " and ")
    text = NON_ALNUM.sub(" ", text)
    text = WS.sub(" ", text).strip()
    text = HOW_TO.sub("", text).strip()
    return text


def slugify(title: str) -> str:
    return normalize_title(title).replace(" ", "-")


def fingerprint(url: str = "", title: str = "") -> dict:
    return {
        "url": normalize_url(url),
        "article_id": article_id(url),
        "title": normalize_title(title),
        "slug": slugify(title),
    }


def _record_fields(record: dict) -> tuple[str, str]:
    url = (
        record.get("source")
        or record.get("source_url")
        or record.get("url")
        or ""
    )
    title = record.get("title") or record.get("episode_title") or ""
    return url, title


def _load_json_list(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("episodes") or data.get("items") or []
    return []


def load_known_episodes() -> list:
    return _load_json_list(KNOWN_FILE)


def load_published_records() -> list:
    return _load_json_list(PUBLISHED_FILE)


def load_pillar_pages() -> list:
    env = (os.getenv("GHL_PILLAR_PAGES") or "").strip()
    pages = []
    if env:
        for part in env.split(","):
            url = part.strip()
            if url:
                pages.append({"url": url, "keywords": [], "title": url.rsplit("/", 1)[-1]})
    pages.extend(_load_json_list(PILLAR_FILE))
    return pages


def _same_topic(left: dict, right: dict) -> bool:
    if left.get("article_id") and left["article_id"] == right.get("article_id"):
        return True
    if left.get("url") and left["url"] == right.get("url"):
        return True
    if left.get("title") and left["title"] == right.get("title"):
        return True
    return False


def match_records(content: dict, records: list, source: str) -> DedupeHit | None:
    probe = fingerprint(
        content.get("source_url") or content.get("source") or content.get("url") or "",
        content.get("title") or "",
    )
    for record in records or []:
        url, title = _record_fields(record)
        other = fingerprint(url, title)
        # Transistor rows may only have a title
        if _same_topic(probe, other):
            return DedupeHit(
                True,
                f"already done ({source}): {title or url or other['title']}",
                source=source,
                matched=url or title,
            )
    return None


def fetch_transistor_episodes(api_key=None, show_id=None, session=None) -> list:
    """List episodes on the configured Transistor show. Empty if creds missing."""
    api_key = api_key or os.getenv("TRANSISTOR_API_KEY")
    show_id = show_id or os.getenv("TRANSISTOR_SHOW_ID")
    if not api_key or not show_id:
        return []

    http = session or requests
    episodes = []
    page = 1
    while page <= 20:
        try:
            resp = http.get(
                "https://api.transistor.fm/v1/episodes",
                params={"show_id": show_id, "pagination[page]": page},
                headers={"x-api-key": api_key},
                timeout=20,
            )
            resp.raise_for_status()
        except requests.RequestException:
            break
        payload = resp.json()
        rows = payload.get("data") or []
        if not rows:
            break
        for row in rows:
            attrs = row.get("attributes") or {}
            episodes.append(
                {
                    "id": row.get("id", ""),
                    "title": attrs.get("title", ""),
                    "source_url": attrs.get("alternate_url") or "",
                    "share_url": attrs.get("share_url", ""),
                    "summary": attrs.get("summary") or attrs.get("description") or "",
                }
            )
        meta = payload.get("meta") or {}
        total_pages = int(meta.get("totalPages") or meta.get("total_pages") or page)
        if page >= total_pages:
            break
        page += 1
    return episodes


def fetch_ghl_site_slugs(site_url=None, session=None) -> list[str]:
    """Optional: slugs already on globalhighlevel.com (sitemap or homepage)."""
    site_url = (site_url or os.getenv("GHL_SITE_DEDUPE_URL") or os.getenv("SITE_URL") or "").strip()
    if not site_url:
        return []
    parsed = urlparse(site_url)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    if host != "globalhighlevel.com" and not host.endswith(".globalhighlevel.com"):
        return []

    http = session or requests
    roots = [
        site_url.rstrip("/") + "/sitemap.xml",
        site_url.rstrip("/") + "/sitemap_index.xml",
        "https://globalhighlevel.com/sitemap.xml",
    ]
    slugs = []
    seen = set()
    for sitemap in roots:
        try:
            resp = http.get(sitemap, timeout=15, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
        except requests.RequestException:
            continue
        for match in re.findall(r"<loc>([^<]+)</loc>", resp.text):
            path = urlparse(match).path.rstrip("/").lower()
            slug = path.rsplit("/", 1)[-1]
            if slug and slug not in seen and slug not in ("", "sitemap.xml"):
                seen.add(slug)
                slugs.append(slug)
        if slugs:
            break
    return slugs


def match_ghl_site(content: dict, slugs: list[str] | None = None) -> DedupeHit | None:
    probe = fingerprint(
        content.get("source_url") or "",
        content.get("title") or "",
    )
    candidates = slugs
    if candidates is None:
        try:
            candidates = fetch_ghl_site_slugs()
        except Exception:
            candidates = []
    for slug in candidates or []:
        if slug and (slug == probe["slug"] or slug == probe["article_id"]):
            return DedupeHit(
                True,
                f"already on globalhighlevel.com (/{slug}) — do not republish or spray a new page",
                source="ghl-site",
                matched=slug,
            )
    for page in load_pillar_pages():
        url = page.get("url") or ""
        title = page.get("title") or ""
        keywords = [k.lower() for k in (page.get("keywords") or [])]
        hay = " ".join([probe["title"], probe["slug"], probe["url"]])
        if probe["slug"] and probe["slug"] == slugify(title):
            return DedupeHit(
                True,
                f"matches existing pillar {url or title}",
                source="ghl-site",
                matched=url or title,
            )
        if any(k and k in hay for k in keywords):
            return DedupeHit(
                True,
                f"matches existing pillar {url or title}",
                source="ghl-site",
                matched=url or title,
            )
    return None


def check_already_done(
    content: dict,
    *,
    published=None,
    known=None,
    transistor_episodes=None,
    site_slugs=None,
    check_transistor=True,
    check_site=True,
) -> DedupeHit:
    """
    Return a DedupeHit. duplicate=True means skip generate and publish.
    """
    if not content:
        return DedupeHit(False, "no content")

    known = known if known is not None else load_known_episodes()
    hit = match_records(content, known, "known")
    if hit:
        return hit

    published = published if published is not None else load_published_records()
    hit = match_records(content, published, "published")
    if hit:
        return hit

    if check_transistor:
        episodes = transistor_episodes
        if episodes is None:
            episodes = fetch_transistor_episodes()
        # Also scan summaries for a source URL fingerprint
        extra = []
        for ep in episodes or []:
            extra.append(ep)
            summary = ep.get("summary") or ""
            urls = re.findall(r"https?://[^\s<\"']+", summary)
            for url in urls:
                extra.append({"title": ep.get("title", ""), "source_url": url})
        hit = match_records(content, extra, "transistor")
        if hit:
            return hit

    if check_site:
        hit = match_ghl_site(content, slugs=site_slugs)
        if hit:
            return hit

    return DedupeHit(False, "new topic")
