"""
Format → channel distribution map.

Source of truth for DISTRIBUTION.md and the publisher dispatcher.
Never invent credentials. Never spray thin HTML onto globalhighlevel.com.
"""

from __future__ import annotations

# status: live | stub | upgrade-only
FORMAT_CHANNEL_MATRIX = {
    "audio": ("transistor", "drive", "social"),
    "video": ("youtube", "drive", "social"),
    "slide-deck": ("drive", "ghl-site"),
    "report": ("drive", "ghl-site", "newsletter"),
    "infographic": ("drive", "social", "ghl-site"),
    "mind-map": ("drive",),
    "quiz": ("drive",),
    "flashcards": ("drive",),
}

CHANNELS = {
    "transistor": {
        "status": "live",
        "owns": "Spotify / Apple / Amazon via Transistor.fm",
        "formats": ("audio",),
        "auth": ("TRANSISTOR_API_KEY", "TRANSISTOR_SHOW_ID"),
        "notes": "Draft then PATCH /publish. Dedupe against show episodes first.",
    },
    "drive": {
        "status": "live",
        "owns": "Google Drive artifacts archive",
        "formats": (
            "audio",
            "video",
            "slide-deck",
            "report",
            "infographic",
            "mind-map",
            "quiz",
            "flashcards",
        ),
        "auth": ("GOOGLE_DRIVE_FOLDER_ID", "GOOGLE_DRIVE_TOKEN or GOOGLE_DRIVE_CREDENTIALS"),
        "notes": "Folder id is config, not a secret. Token/service-account files stay local.",
    },
    "youtube": {
        "status": "stub",
        "owns": "YouTube long-form + Shorts",
        "formats": ("video",),
        "auth": ("YOUTUBE_CLIENT_SECRETS", "YOUTUBE_TOKEN"),
        "notes": "Need channel OAuth later. Do not invent client ids.",
    },
    "ghl-site": {
        "status": "upgrade-only",
        "owns": "globalhighlevel.com existing pillars / money pages",
        "formats": ("report", "slide-deck", "infographic"),
        "auth": ("GHL_PILLAR_PAGES or data/pillar-pages.json",),
        "notes": (
            "Fold into an existing pillar only. NEVER create a thin new HTML post. "
            "Prior Google demotion came from ~850 thin NotebookLM pages."
        ),
    },
    "social": {
        "status": "stub",
        "owns": "LinkedIn / X / Facebook",
        "formats": ("audio", "video", "infographic"),
        "auth": ("SOCIAL_BUFFER_ACCESS_TOKEN or SOCIAL_API_TOKEN",),
        "notes": "Stub until a real Buffer/native token exists.",
    },
    "newsletter": {
        "status": "stub",
        "owns": "Beehiiv / Substack",
        "formats": ("report",),
        "auth": ("BEEHIIV_API_KEY or SUBSTACK_PUBLICATION_URL",),
        "notes": "Stub only unless GHL already has a list. Do not invent a publication.",
    },
}


def channels_for_format(fmt: str) -> tuple[str, ...]:
    return FORMAT_CHANNEL_MATRIX.get(fmt, ("drive",))


def required_auth(channel: str) -> tuple[str, ...]:
    info = CHANNELS.get(channel) or {}
    return tuple(info.get("auth") or ())
