"""
Pluggable publishers for the GHL AI multi-format lane.

Transistor (audio) is implemented. YouTube, Drive, and social are real
hooks that run when credentials exist and otherwise skip with an explicit
TODO — they never invent keys.

HARD: never publish thin new HTML pages to globalhighlevel.com.
"""

from __future__ import annotations

import os
from pathlib import Path

from scripts.source_filter import is_thin_site_destination

# Channels this module knows about. AI lane never writes HTML to the marketing site.
CHANNELS = ("transistor", "youtube", "drive", "social")


def _missing(env_names):
    return [name for name in env_names if not (os.getenv(name) or "").strip()]


def _refuse_thin_site(destination: str | None) -> dict | None:
    if destination and is_thin_site_destination(destination):
        return {
            "channel": "blocked",
            "status": "blocked",
            "url": destination,
            "reason": "HARD: no thin new HTML pages on globalhighlevel.com",
        }
    return None


def publish_transistor(audio_path, title, description="", tags=None, transcript=""):
    """Publish audio to Transistor.fm using the canary draft-then-publish flow."""
    if not audio_path or not Path(audio_path).exists():
        return {
            "channel": "transistor",
            "status": "skipped",
            "url": "",
            "reason": "no local audio artifact",
        }
    missing = _missing(("TRANSISTOR_API_KEY", "TRANSISTOR_SHOW_ID"))
    if missing:
        return {
            "channel": "transistor",
            "status": "skipped",
            "url": "",
            "reason": f"missing {', '.join(missing)} — set in .env, do not invent credentials",
        }
    from scripts.upload import upload_episode

    result = upload_episode(
        audio_path=audio_path,
        title=title,
        description=description,
        tags=tags or [],
        transcript=transcript or "",
    )
    return {
        "channel": "transistor",
        "status": result.get("status") or "published",
        "url": result.get("share_url", ""),
        "id": result.get("id", ""),
        "reason": "published via draft-then-PATCH /publish",
    }


def publish_youtube(video_path, title, description=""):
    """
    YouTube upload hook.

    TODO: implement YouTube Data API v3 resumable upload when
    YOUTUBE_CLIENT_SECRETS (or credentials.json) and token.json exist.
    Do not invent OAuth client IDs or refresh tokens.
    """
    blocked = _refuse_thin_site(os.getenv("YOUTUBE_CANONICAL_URL"))
    if blocked:
        blocked["channel"] = "youtube"
        return blocked
    if not video_path or not Path(str(video_path)).exists():
        return {
            "channel": "youtube",
            "status": "skipped",
            "url": "",
            "reason": "no local video artifact",
        }
    secrets = os.getenv("YOUTUBE_CLIENT_SECRETS") or os.getenv("YOUTUBE_CREDENTIALS")
    token = os.getenv("YOUTUBE_TOKEN")
    if not secrets or not token or not Path(secrets).exists() or not Path(token).exists():
        return {
            "channel": "youtube",
            "status": "skipped",
            "url": "",
            "reason": (
                "TODO: YouTube Data API upload. Need YOUTUBE_CLIENT_SECRETS + "
                "YOUTUBE_TOKEN files from OAuth. Credentials are not in this repo."
            ),
        }
    # Real hook: files exist. Still do not guess an upload implementation that
    # would require scopes we cannot verify here.
    return {
        "channel": "youtube",
        "status": "skipped",
        "url": "",
        "reason": (
            "TODO: credentials files are present — wire googleapiclient videos.insert "
            f"for {title!r} ({video_path}). Not implemented in this canary."
        ),
    }


def publish_drive(artifact_path, title, mime_type=""):
    """
    Google Drive upload hook.

    TODO: implement Drive files.create when GOOGLE_DRIVE_FOLDER_ID and a
    valid OAuth token exist. Do not invent folder IDs or service-account JSON.
    """
    blocked = _refuse_thin_site(os.getenv("DRIVE_SHARE_URL"))
    if blocked:
        blocked["channel"] = "drive"
        return blocked
    if not artifact_path or not Path(str(artifact_path)).exists():
        return {
            "channel": "drive",
            "status": "skipped",
            "url": "",
            "reason": "no local artifact to upload",
        }
    folder = (os.getenv("GOOGLE_DRIVE_FOLDER_ID") or "").strip()
    creds = os.getenv("GOOGLE_DRIVE_CREDENTIALS") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    token = os.getenv("GOOGLE_DRIVE_TOKEN")
    have_creds = bool(folder) and (
        (creds and Path(creds).exists()) or (token and Path(token).exists())
    )
    if not have_creds:
        return {
            "channel": "drive",
            "status": "skipped",
            "url": "",
            "reason": (
                "TODO: Drive files.create. Need GOOGLE_DRIVE_FOLDER_ID plus "
                "GOOGLE_DRIVE_CREDENTIALS or GOOGLE_DRIVE_TOKEN. Do not invent them."
            ),
        }
    return {
        "channel": "drive",
        "status": "skipped",
        "url": "",
        "reason": (
            f"TODO: credentials present — upload {title!r} ({artifact_path}) to "
            f"folder {folder}. Not implemented in this canary."
        ),
    }


def publish_social(artifact_path, title, description=""):
    """
    Social scheduling hook (Buffer / native APIs).

    TODO: post when SOCIAL_BUFFER_ACCESS_TOKEN (or native tokens) exist.
    Do not invent tokens. Never open a thin page on globalhighlevel.com.
    """
    site = os.getenv("SOCIAL_CANONICAL_URL") or os.getenv("SITE_URL")
    blocked = _refuse_thin_site(site)
    if blocked:
        blocked["channel"] = "social"
        return blocked
    token = (os.getenv("SOCIAL_BUFFER_ACCESS_TOKEN") or os.getenv("SOCIAL_API_TOKEN") or "").strip()
    if not token:
        return {
            "channel": "social",
            "status": "skipped",
            "url": "",
            "reason": (
                "TODO: Buffer/native social post. Set SOCIAL_BUFFER_ACCESS_TOKEN "
                "(or SOCIAL_API_TOKEN) in .env. Do not invent tokens. "
                "Do not publish thin HTML to globalhighlevel.com."
            ),
        }
    return {
        "channel": "social",
        "status": "skipped",
        "url": "",
        "reason": (
            f"TODO: token present — schedule social post for {title!r} "
            f"({artifact_path}). Not implemented in this canary."
        ),
    }


def publish_artifacts(artifacts, content, seo_data=None, channels=None):
    """
    Fan artifacts out to configured publishers.

    Audio → Transistor (real). Video → YouTube hook. Every file → Drive hook.
    Visual/audio → social hook. Missing creds skip; thin-site dests block.
    """
    seo_data = seo_data or {}
    title = seo_data.get("title") or content.get("title") or "GHL AI"
    description = seo_data.get("description") or ""
    tags = seo_data.get("tags") or []
    wanted = set(channels or CHANNELS)
    results = []

    dest = content.get("publish_url") or os.getenv("SITE_URL")
    blocked = _refuse_thin_site(dest)
    if blocked:
        return [blocked]

    by_fmt = {a.get("format"): a for a in (artifacts or [])}

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
        video = by_fmt.get("video") or {}
        results.append(publish_youtube(video.get("path"), title, description=description))

    if "drive" in wanted:
        if artifacts:
            for art in artifacts:
                results.append(publish_drive(art.get("path"), f"{title} ({art.get('format')})"))
        else:
            results.append(publish_drive("", title))

    if "social" in wanted:
        visual = by_fmt.get("infographic") or by_fmt.get("video") or by_fmt.get("audio") or {}
        results.append(publish_social(visual.get("path"), title, description=description))

    return results
