"""
Publishers for the GHL AI multi-format lane.

See DISTRIBUTION.md and scripts/distribution.py for the format→channel matrix.

HARD:
  - never invent credentials
  - never spray thin new HTML onto globalhighlevel.com
  - only fold into existing pillars when a match exists
  - Drive is not an audience; local scratch under data/ is fine
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from scripts.distribution import CHANNELS, FORMAT_CHANNEL_MATRIX
from scripts.seo import with_trial_cta
from scripts.source_filter import is_thin_site_destination

BASE_DIR = Path(__file__).parent.parent
UPGRADE_DIR = BASE_DIR / "data" / "site-upgrades"

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_TOKEN_URI = "https://oauth2.googleapis.com/token"
YOUTUBE_TITLE_MAX = 100
YOUTUBE_DESC_MAX = 5000
DEFAULT_YOUTUBE_PRIVACY = "unlisted"


def _missing(env_names):
    return [name for name in env_names if not (os.getenv(name) or "").strip()]


_SECRET_IN_TEXT = re.compile(
    r"(ya29\.[A-Za-z0-9._-]+|1//[A-Za-z0-9._-]+|"
    r"(?i)(?:client_secret|refresh_token|access_token)\s*[:=]\s*\S+)"
)


def _safe_exc(exc: Exception) -> str:
    """Keep error type; strip token-shaped values from the reason string."""
    text = _SECRET_IN_TEXT.sub("[redacted]", f"{type(exc).__name__}: {exc}")
    return text[:240]


def _result(channel, status, reason, url="", extra=None):
    out = {"channel": channel, "status": status, "url": url, "reason": reason}
    if extra:
        out.update(extra)
    return out


def _refuse_thin_new_page(destination: str | None):
    if destination and is_thin_site_destination(destination):
        return _result(
            "ghl-site",
            "blocked",
            "HARD: no thin new HTML pages on globalhighlevel.com",
            url=destination,
        )
    return None


def publish_transistor(audio_path, title, description="", tags=None, transcript=""):
    """Publish audio to Transistor.fm (Spotify/Apple/etc). Live."""
    if not audio_path or not Path(audio_path).exists():
        return _result("transistor", "skipped", "no local audio artifact")
    missing = _missing(("TRANSISTOR_API_KEY", "TRANSISTOR_SHOW_ID"))
    if missing:
        return _result(
            "transistor",
            "skipped",
            f"missing {', '.join(missing)} — set in .env, do not invent credentials",
        )
    from scripts.upload import upload_episode

    result = upload_episode(
        audio_path=audio_path,
        title=title,
        description=with_trial_cta(description),
        tags=tags or [],
        transcript=transcript or "",
    )
    return _result(
        "transistor",
        result.get("status") or "published",
        "published via draft-then-PATCH /publish → Spotify/Apple/Amazon",
        url=result.get("share_url", ""),
        extra={"id": result.get("id", "")},
    )


def resolve_youtube_privacy(raw=None):
    """unlisted (default, canary) or public. Anything else falls back to unlisted."""
    value = (raw if raw is not None else os.getenv("YOUTUBE_PRIVACY") or DEFAULT_YOUTUBE_PRIVACY)
    value = str(value).strip().lower()
    if value in ("unlisted", "public"):
        return value
    return DEFAULT_YOUTUBE_PRIVACY


def youtube_oauth_paths():
    """Env paths only. Never invent or bake client ids / tokens."""
    secrets = (os.getenv("YOUTUBE_CLIENT_SECRETS") or os.getenv("YOUTUBE_CREDENTIALS") or "").strip()
    token = (os.getenv("YOUTUBE_TOKEN") or "").strip()
    return secrets, token


def oauth_client_fields(secrets_path, token_path):
    """Merge token JSON with installed/web client secrets. Paths only — no defaults."""
    token_data = json.loads(Path(token_path).read_text(encoding="utf-8"))
    secrets_data = json.loads(Path(secrets_path).read_text(encoding="utf-8"))
    if not isinstance(token_data, dict) or not isinstance(secrets_data, dict):
        raise ValueError("YouTube OAuth JSON must be objects")
    client = secrets_data.get("installed") or secrets_data.get("web") or secrets_data
    if not isinstance(client, dict):
        raise ValueError("YouTube client secrets missing installed/web object")
    scopes = token_data.get("scopes") or [YOUTUBE_UPLOAD_SCOPE]
    if isinstance(scopes, str):
        scopes = [scopes]
    return {
        "token": token_data.get("token") or token_data.get("access_token") or None,
        "refresh_token": token_data.get("refresh_token") or None,
        "token_uri": token_data.get("token_uri") or client.get("token_uri") or YOUTUBE_TOKEN_URI,
        "client_id": token_data.get("client_id") or client.get("client_id") or None,
        "client_secret": token_data.get("client_secret") or client.get("client_secret") or None,
        "scopes": list(scopes),
    }


def refresh_youtube_credentials(creds, request_factory=None):
    """Refresh via google.oauth2.credentials + Request when expired / invalid."""
    if request_factory is None:
        from google.auth.transport.requests import Request

        request_factory = Request
    needs_refresh = bool(getattr(creds, "refresh_token", None)) and (
        not getattr(creds, "valid", True) or getattr(creds, "expired", False)
    )
    if not needs_refresh:
        return False
    creds.refresh(request_factory())
    return True


def load_youtube_credentials(secrets_path, token_path):
    """Build Credentials from env file paths and persist a refreshed token."""
    from google.oauth2.credentials import Credentials

    fields = oauth_client_fields(secrets_path, token_path)
    if not fields.get("client_id") or not fields.get("refresh_token"):
        raise ValueError("YouTube OAuth files need client_id and refresh_token")
    creds = Credentials(
        token=fields["token"],
        refresh_token=fields["refresh_token"],
        token_uri=fields["token_uri"],
        client_id=fields["client_id"],
        client_secret=fields["client_secret"],
        scopes=fields["scopes"],
    )
    if refresh_youtube_credentials(creds):
        Path(token_path).write_text(creds.to_json(), encoding="utf-8")
        try:
            os.chmod(token_path, 0o600)
        except OSError:
            pass
    return creds


def _insert_youtube_video(creds, video_path, title, description, privacy):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {
        "snippet": {
            "title": (title or "GHL AI")[:YOUTUBE_TITLE_MAX],
            "description": (description or "")[:YOUTUBE_DESC_MAX],
        },
        "status": {"privacyStatus": privacy},
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    return (
        youtube.videos()
        .insert(part="snippet,status", body=body, media_body=media)
        .execute()
    )


def publish_youtube(video_path, title, description=""):
    """Upload a local video via YouTube Data API videos.insert. Skip without real OAuth files."""
    if not video_path or not Path(str(video_path)).exists():
        return _result("youtube", "skipped", "no local video artifact")
    secrets, token = youtube_oauth_paths()
    if not secrets or not token or not Path(secrets).exists() or not Path(token).exists():
        return _result(
            "youtube",
            "skipped",
            "Need YOUTUBE_CLIENT_SECRETS + YOUTUBE_TOKEN file paths "
            "(channel OAuth). Do not invent client ids.",
        )
    description = with_trial_cta(description)
    privacy = resolve_youtube_privacy()
    try:
        creds = load_youtube_credentials(secrets, token)
        response = _insert_youtube_video(creds, video_path, title, description, privacy)
    except Exception as exc:
        return _result(
            "youtube",
            "error",
            f"videos.insert failed: {_safe_exc(exc)}",
        )
    video_id = (response or {}).get("id") or ""
    url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
    return _result(
        "youtube",
        "published",
        f"uploaded via videos.insert ({privacy}) to @williamcourterwelch",
        url=url,
        extra={"id": video_id, "privacy": privacy},
    )


def _match_pillar(content, seo_data=None):
    from scripts.dedupe import load_pillar_pages, normalize_title

    hay = " ".join(
        [
            (content or {}).get("title") or "",
            (seo_data or {}).get("title") or "",
            (content or {}).get("source_url") or "",
            " ".join((seo_data or {}).get("tags") or []),
        ]
    ).lower()
    title_norm = normalize_title((seo_data or {}).get("title") or (content or {}).get("title") or "")
    for page in load_pillar_pages():
        url = (page.get("url") or "").strip()
        if not url:
            continue
        keywords = [k.lower() for k in (page.get("keywords") or [])]
        page_title = normalize_title(page.get("title") or "")
        if page_title and page_title == title_norm:
            return page
        if any(k and k in hay for k in keywords):
            return page
    return None


def publish_ghl_site(content, seo_data=None, artifacts=None):
    """
    Upgrade an existing globalhighlevel.com pillar only.

    Never writes a new public HTML page. If no pillar matches, skip.
    When a pillar matches, write a local fold brief under data/site-upgrades/
    (and optionally POST GHL_SITE_UPGRADE_WEBHOOK if set).
    """
    dest = (content or {}).get("publish_url") or os.getenv("SITE_URL")
    blocked = _refuse_thin_new_page(dest)
    if blocked and not _match_pillar(content, seo_data):
        return blocked

    pillar = _match_pillar(content, seo_data)
    if not pillar:
        return _result(
            "ghl-site",
            "skipped",
            "no matching pillar/money page — refusing a thin new HTML post on "
            "globalhighlevel.com (prior Google demotion from ~850 thin pages)",
        )

    UPGRADE_DIR.mkdir(parents=True, exist_ok=True)
    slug = (pillar.get("url") or "pillar").rstrip("/").rsplit("/", 1)[-1] or "pillar"
    brief_path = UPGRADE_DIR / f"{slug}-{datetime.now().strftime('%Y%m%d')}.json"
    brief = {
        "action": "fold-into-existing-page",
        "pillar_url": pillar.get("url"),
        "pillar_title": pillar.get("title"),
        "source_url": (content or {}).get("source_url"),
        "title": (seo_data or {}).get("title") or (content or {}).get("title"),
        "artifacts": artifacts or [],
        "rule": "Do not create a new URL. Upgrade the existing pillar only.",
        "written_at": datetime.now().isoformat(),
    }
    brief_path.write_text(json.dumps(brief, indent=2), encoding="utf-8")

    webhook = (os.getenv("GHL_SITE_UPGRADE_WEBHOOK") or "").strip()
    if webhook:
        try:
            import requests

            requests.post(webhook, json=brief, timeout=20)
            return _result(
                "ghl-site",
                "queued-upgrade",
                f"folded into existing pillar {pillar.get('url')} via webhook",
                url=pillar.get("url", ""),
                extra={"brief": str(brief_path)},
            )
        except Exception as exc:
            return _result(
                "ghl-site",
                "queued-upgrade",
                f"brief written; webhook failed ({exc})",
                url=pillar.get("url", ""),
                extra={"brief": str(brief_path)},
            )

    return _result(
        "ghl-site",
        "queued-upgrade",
        f"fold brief for existing pillar {pillar.get('url')} — no new HTML page",
        url=pillar.get("url", ""),
        extra={"brief": str(brief_path)},
    )


def publish_social(artifact_path, title, description=""):
    """LinkedIn / X / Facebook. Stub until a real token exists."""
    token = (os.getenv("SOCIAL_BUFFER_ACCESS_TOKEN") or os.getenv("SOCIAL_API_TOKEN") or "").strip()
    if not token:
        return _result(
            "social",
            "skipped",
            "TODO: LinkedIn/X/FB via Buffer or native APIs. Set "
            "SOCIAL_BUFFER_ACCESS_TOKEN (or SOCIAL_API_TOKEN). Do not invent tokens.",
        )
    return _result(
        "social",
        "skipped",
        f"TODO: token present — schedule LinkedIn/X/FB for {title!r}. Stub only.",
    )


def publish_artifacts(artifacts, content, seo_data=None, channels=None):
    """
    Fan artifacts to the audience map.

    Default channels come from FORMAT_CHANNEL_MATRIX. Missing creds skip.
    Thin new globalhighlevel.com pages are blocked.
    Drive is not a destination. Empty-matrix formats stay in data/.
    """
    seo_data = seo_data or {}
    title = seo_data.get("title") or content.get("title") or "GHL AI"
    description = seo_data.get("description") or ""
    tags = seo_data.get("tags") or []
    by_fmt = {a.get("format"): a for a in (artifacts or [])}

    wanted = set(channels) if channels else set()
    if not wanted:
        for fmt in by_fmt:
            wanted.update(FORMAT_CHANNEL_MATRIX.get(fmt, ()))
        if not by_fmt:
            wanted.update(CHANNELS)

    dest = content.get("publish_url") or os.getenv("SITE_URL")
    results = []
    if dest and is_thin_site_destination(dest) and "ghl-site" not in wanted:
        # Explicit new-page dest with no upgrade path → hard block the bundle
        # unless ghl-site is in the map (upgrade-only handler decides).
        blocked = _refuse_thin_new_page(dest)
        if blocked:
            return [blocked]

    if "transistor" in wanted:
        audio = by_fmt.get("audio") or {}
        results.append(
            publish_transistor(
                audio.get("path"),
                title,
                description=description,
                tags=tags,
            )
        )

    if "youtube" in wanted:
        video = by_fmt.get("video") or by_fmt.get("cinematic-video") or {}
        results.append(publish_youtube(video.get("path"), title, description=description))

    if "ghl-site" in wanted:
        results.append(publish_ghl_site(content, seo_data=seo_data, artifacts=artifacts or []))

    if "social" in wanted:
        visual = by_fmt.get("infographic") or by_fmt.get("video") or by_fmt.get("audio") or {}
        results.append(publish_social(visual.get("path"), title, description=description))

    return results
