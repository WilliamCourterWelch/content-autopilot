"""
Topic picker for the GHL AI Studio lane.

Pipeline (HARD, default --limit 1):
  1. Scrape recent help.gohighlevel.com + changelog for GHL AI keywords
  2. Hard dedupe vs Transistor + published.json + site
  3. Rank remaining topics by money-adjacent score
  4. Return the top N (default 1)

Drive is not part of this. Local scratch under data/ is fine.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scripts.dedupe import check_already_done
from scripts.source_filter import classify_ghl_ai_source, filter_sources

USER_AGENT = "ContentAutopilot-TopicPicker/1.0"

# Ready AI-lane candidates from the 2026-09-16 canary report (fallback only).
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
    "AI receptionist",
    "Voice AI agent",
)

CHANGELOG_INDEX_URLS = (
    "https://ideas.gohighlevel.com/changelog",
    "https://changelog.gohighlevel.com/",
    "https://updates.gohighlevel.com/",
    "https://help.gohighlevel.com/support/solutions",
)

# Money-adjacent: labor replacement, inbound/outbound, booking, conversion.
# These rank above generic AI how-tos.
TIER1_MONEY = (
    "conversation ai",
    "voice ai",
    "ai employee",
    "ai receptionist",
    "ai inbound",
    "ai outbound",
    "ai caller",
    "ai calling",
    "voice agent",
)

TIER2_MONEY = (
    "appointment",
    "booking",
    "lead",
    "sales",
    "closer",
    "qualify",
    "pipeline",
    "revenue",
    "conversion",
    "missed call",
    "after hours",
    "agent transfer",
    "follow up",
    "follow-up",
    "knowledge base",
    "inbound",
    "outbound",
    "receptionist",
)

_DATE_PATTERNS = (
    re.compile(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})"),
    re.compile(
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(\d{1,2}),?\s+(20\d{2})",
        re.I,
    ),
)
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _get(url: str, timeout: int = 15):
    return requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})


def _hay(item: dict) -> str:
    return " ".join(
        [
            item.get("source_url") or item.get("url") or "",
            item.get("title") or "",
            item.get("snippet") or item.get("body") or item.get("summary") or "",
        ]
    ).lower()


def parse_recent_date(*texts: str) -> datetime | None:
    """Best-effort date from title/snippet/URL. Naive UTC."""
    blob = " ".join(t or "" for t in texts)
    for match in _DATE_PATTERNS[0].finditer(blob):
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            continue
    for match in _DATE_PATTERNS[1].finditer(blob):
        month = _MONTHS.get(match.group(1).lower()[:4]) or _MONTHS.get(match.group(1).lower()[:3])
        day, year = int(match.group(2)), int(match.group(3))
        if not month:
            continue
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def money_adjacent_score(item: dict, now: datetime | None = None) -> int:
    """
    Higher = more money-adjacent and more recent.

    Conversation AI / Voice AI / AI employee beat generic chatbot how-tos.
    Changelog hosts get a recency bump. Parsed dates within 90 days score extra.
    """
    hay = _hay(item)
    score = 0
    for kw in TIER1_MONEY:
        if kw in hay:
            score += 5
    for kw in TIER2_MONEY:
        if kw in hay:
            score += 3

    url = item.get("source_url") or item.get("url") or ""
    host = (urlparse(url).netloc or "").lower()
    if host.startswith(("ideas.", "changelog.", "updates.")):
        score += 4
    if item.get("_ai_filter", {}).get("kind") == "ai-changelog":
        score += 2

    when = item.get("published_at")
    if isinstance(when, str):
        when = parse_recent_date(when)
    if not isinstance(when, datetime):
        when = parse_recent_date(url, item.get("title") or "", item.get("snippet") or "")
    if when:
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        now = now or datetime.now(timezone.utc)
        age_days = (now - when).days
        if age_days <= 30:
            score += 6
        elif age_days <= 90:
            score += 3
        elif age_days <= 180:
            score += 1

    return score


def _article_href(href: str, base: str) -> str | None:
    if not href:
        return None
    full = urljoin(base, href).split("#")[0].split("?")[0]
    path = (urlparse(full).path or "").lower()
    host = (urlparse(full).netloc or "").lower()
    if "/support/solutions/articles/" in path:
        return full
    if host.startswith(("ideas.", "changelog.", "updates.")) and "/changelog/" in path:
        tail = path.rstrip("/").rsplit("/", 1)[-1]
        if tail and tail not in ("changelog", "page"):
            return full
    if host.endswith("gohighlevel.com") and any(
        hint in path for hint in ("/updates/", "/whats-new/", "/release-notes/")
    ):
        tail = path.rstrip("/").rsplit("/", 1)[-1]
        if tail and tail not in ("updates", "whats-new", "release-notes"):
            return full
    return None


def _collect_links(html: str, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = _article_href(a["href"], base)
        if not href or href in seen:
            continue
        seen.add(href)
        title = a.get_text(" ", strip=True)
        parent = a.find_parent(["article", "li", "div", "tr"])
        snippet = parent.get_text(" ", strip=True)[:400] if parent else title
        found.append(
            {
                "source_url": href,
                "url": href,
                "title": title or href.rsplit("/", 1)[-1].replace("-", " "),
                "snippet": snippet,
            }
        )
    return found


def scrape_help_search(limit_per_term: int = 12, session=None) -> list[dict]:
    http = session or requests
    found = []
    seen = set()
    for term in SEARCH_TERMS:
        url = HELP_SEARCH.format(term=quote_plus(term))
        try:
            resp = http.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
        except requests.RequestException:
            continue
        for item in _collect_links(resp.text, url):
            href = item["source_url"]
            if href in seen:
                continue
            seen.add(href)
            item["picker_source"] = "help-search"
            found.append(item)
            if len([i for i in found if i.get("picker_source") == "help-search"]) >= limit_per_term * len(
                SEARCH_TERMS
            ):
                return found
    return found


def scrape_changelog_indexes(session=None) -> list[dict]:
    http = session or requests
    found = []
    seen = set()
    for url in CHANGELOG_INDEX_URLS:
        try:
            resp = http.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
        except requests.RequestException:
            continue
        for item in _collect_links(resp.text, url):
            href = item["source_url"]
            if href in seen:
                continue
            seen.add(href)
            item["picker_source"] = "changelog"
            found.append(item)
    return found


def collect_candidates(extra_urls=None, include_seeds=True, session=None) -> list[dict]:
    """Scrape help + changelog, plus optional extras / seeds. AI filter applied."""
    raw = []
    if extra_urls:
        for url in extra_urls:
            if not url:
                continue
            raw.append(
                {
                    "source_url": url,
                    "url": url,
                    "title": url.rsplit("/", 1)[-1].replace("-", " "),
                    "snippet": "",
                    "picker_source": "extra",
                }
            )
    if include_seeds:
        for url in SEED_AI_URLS:
            raw.append(
                {
                    "source_url": url,
                    "url": url,
                    "title": url.rsplit("/", 1)[-1].replace("-", " "),
                    "snippet": "",
                    "picker_source": "seed",
                }
            )
    try:
        raw.extend(scrape_help_search(session=session))
    except Exception:
        pass
    try:
        raw.extend(scrape_changelog_indexes(session=session))
    except Exception:
        pass

    unique = []
    seen = set()
    for item in raw:
        url = item.get("source_url") or item.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(item)
    return filter_sources(unique, require_ai=True)


def hard_dedupe(candidates, *, transistor_episodes=None, published=None, site_slugs=None) -> list[dict]:
    """Drop anything already in published.json, Transistor, known-episodes, or site."""
    kept = []
    for item in candidates or []:
        content = {
            "source_url": item.get("source_url") or item.get("url") or "",
            "title": item.get("title") or "",
        }
        hit = check_already_done(
            content,
            published=published,
            transistor_episodes=transistor_episodes,
            site_slugs=site_slugs,
            check_transistor=True,
            check_site=True,
        )
        if hit.duplicate:
            continue
        item = dict(item)
        item["_dedupe"] = {"reason": hit.reason, "duplicate": False}
        kept.append(item)
    return kept


def rank_money_adjacent(candidates, now: datetime | None = None) -> list[dict]:
    """Sort new AI topics: money-adjacent + recent first. Ties keep scrape order."""
    scored = []
    for index, item in enumerate(candidates or []):
        row = dict(item)
        row["_rank"] = money_adjacent_score(row, now=now)
        row["_order"] = index
        scored.append(row)
    scored.sort(key=lambda r: (-r["_rank"], r["_order"]))
    return scored


def pick_topics(
    limit: int = 1,
    extra_urls=None,
    include_seeds=True,
    session=None,
    transistor_episodes=None,
    published=None,
    site_slugs=None,
    now: datetime | None = None,
) -> list[dict]:
    """
    Scrape → hard dedupe → rank money-adjacent → top `limit` (default 1).
    """
    limit = int(limit or 1)
    if limit < 1:
        limit = 1
    candidates = collect_candidates(
        extra_urls=extra_urls,
        include_seeds=include_seeds,
        session=session,
    )
    fresh = hard_dedupe(
        candidates,
        transistor_episodes=transistor_episodes,
        published=published,
        site_slugs=site_slugs,
    )
    ranked = rank_money_adjacent(fresh, now=now)
    return ranked[:limit]
