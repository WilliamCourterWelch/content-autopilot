"""
GHL AI source allowlist.

Default: only help.gohighlevel.com (and changelog) articles about GHL AI
features (Conversation AI, Voice AI, agents). Reject random non-AI spray.

Publishing to globalhighlevel.com with thin new HTML is a hard no — that
check lives here so callers can refuse a destination before any write.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

# Official source hosts for the AI lane. Marketing/homepage spray is out.
ALLOWED_SOURCE_HOSTS = (
    "help.gohighlevel.com",
    "ideas.gohighlevel.com",
    "changelog.gohighlevel.com",
    "updates.gohighlevel.com",
)

# Extra path hints when the host is a gohighlevel.com property.
CHANGELOG_PATH_HINTS = (
    "/changelog",
    "/updates",
    "/whats-new",
    "/release-notes",
)

# Destination we must never fill with thin generated HTML pages.
THIN_SITE_HOSTS = (
    "globalhighlevel.com",
    "www.globalhighlevel.com",
)

AI_KEYWORDS = (
    "conversation ai",
    "conversation-ai",
    "conversational ai",
    "voice ai",
    "voice-ai",
    "voice agent",
    "ai agent",
    "ai agents",
    "ai employee",
    "ai bot",
    "ai assistant",
    "ghl ai",
    "highlevel ai",
    "go high level ai",
    "gohighlevel ai",
    "chatbot",
    "chat bot",
    "knowledge base ai",
    "ai inbound",
    "ai outbound",
    "ai receptionist",
    "ai caller",
    "ai calling",
    "smart voice",
    "agent transfer",
    "agents dashboard",
    "conversation ai bot",
    "conversation ai agents",
)

# Slug tokens that count even when title/body is thin (help article URLs).
AI_SLUG_TOKENS = (
    "conversation-ai",
    "voice-ai",
    "ai-agent",
    "ai-bot",
    "ai-employee",
    "chatbot",
    "voice-agent",
)


@dataclass(frozen=True)
class FilterResult:
    accepted: bool
    reason: str
    matched: tuple[str, ...] = field(default_factory=tuple)
    host: str = ""
    kind: str = ""  # "ai-help" | "ai-changelog" | "rejected" | "thin-site"


def _host(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _haystack(url: str, title: str = "", body: str = "") -> str:
    path = ""
    try:
        path = urlparse(url).path or ""
    except Exception:
        path = ""
    return " ".join([url or "", path, title or "", (body or "")[:4000]]).lower()


def _keyword_hits(text: str) -> tuple[str, ...]:
    hits = [kw for kw in AI_KEYWORDS if kw in text]
    for token in AI_SLUG_TOKENS:
        if token in text and token.replace("-", " ") not in hits and token not in hits:
            hits.append(token)
    # preserve order, unique
    seen = set()
    out = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return tuple(out)


def is_allowed_source_host(url: str) -> bool:
    host = _host(url)
    if host in ALLOWED_SOURCE_HOSTS:
        return True
    # Allow gohighlevel.com changelog-style paths, not the whole marketing site.
    if host.endswith("gohighlevel.com") and any(
        hint in (urlparse(url).path or "").lower() for hint in CHANGELOG_PATH_HINTS
    ):
        return True
    return False


def is_thin_site_destination(url: str) -> bool:
    """True if this would publish a new page onto globalhighlevel.com."""
    host = _host(url)
    return host in THIN_SITE_HOSTS or host.endswith(".globalhighlevel.com")


def classify_ghl_ai_source(
    url: str,
    title: str = "",
    body: str = "",
    require_ai: bool = True,
) -> FilterResult:
    """
    Accept help/changelog URLs about GHL AI features.

    require_ai=True (default) rejects calendar/payments/unrelated how-tos even
    when they live on help.gohighlevel.com. Pass require_ai=False only as an
    explicit escape hatch — the AI lane never does that by default.
    """
    url = (url or "").strip()
    host = _host(url)

    if not url:
        return FilterResult(False, "missing URL", host=host, kind="rejected")

    if is_thin_site_destination(url):
        return FilterResult(
            False,
            "HARD: no thin new HTML pages on globalhighlevel.com",
            host=host,
            kind="thin-site",
        )

    if not is_allowed_source_host(url):
        return FilterResult(
            False,
            f"host {host or '(none)'} is not a GHL help/changelog source",
            host=host,
            kind="rejected",
        )

    hits = _keyword_hits(_haystack(url, title, body))
    changelog = host.startswith("ideas.") or host.startswith("changelog.") or host.startswith(
        "updates."
    ) or any(h in (urlparse(url).path or "").lower() for h in CHANGELOG_PATH_HINTS)

    if require_ai and not hits:
        return FilterResult(
            False,
            "not a GHL AI feature article (Conversation AI / Voice AI / agents)",
            host=host,
            kind="rejected",
        )

    kind = "ai-changelog" if changelog else "ai-help"
    reason = (
        f"matched {', '.join(hits[:4])}" if hits else "help/changelog host (AI filter off)"
    )
    return FilterResult(True, reason, matched=hits, host=host, kind=kind)


def is_ghl_ai_source(url: str, title: str = "", body: str = "", require_ai: bool = True) -> bool:
    return classify_ghl_ai_source(url, title=title, body=body, require_ai=require_ai).accepted


def filter_sources(items, require_ai: bool = True) -> list:
    """
    Filter an iterable of dicts or URL strings. Keeps accepted GHL AI sources.

    Each item may be a URL string or a dict with source_url/url/title/body.
    Accepted dicts gain `_ai_filter` (FilterResult as dict).
    """
    kept = []
    for item in items or []:
        if isinstance(item, str):
            url, title, body = item, "", ""
            payload = {"source_url": url}
        else:
            payload = dict(item)
            url = payload.get("source_url") or payload.get("url") or ""
            title = payload.get("title") or ""
            body = payload.get("body") or payload.get("summary") or ""
        result = classify_ghl_ai_source(url, title=title, body=body, require_ai=require_ai)
        if result.accepted:
            payload["_ai_filter"] = {
                "reason": result.reason,
                "matched": list(result.matched),
                "kind": result.kind,
            }
            if "source_url" not in payload:
                payload["source_url"] = url
            kept.append(payload)
    return kept
