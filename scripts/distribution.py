"""
Format → channel distribution map.

Source of truth for DISTRIBUTION.md and the publisher dispatcher.
Never invent credentials. Never spray thin HTML onto globalhighlevel.com.

Google Drive is NOT a publish destination. Drive is not an audience.
Local scratch under data/ is fine; do not treat a Drive folder as distribution.

Publish targets only:
  - Transistor / Spotify (audio)
  - YouTube (video)
  - globalhighlevel.com pillar / money-page FOLDS only
  - social stubs
"""

from __future__ import annotations

# status: live | stub | upgrade-only | local-scratch
# Empty channel tuple = local scratch only (data/), not an audience.
FORMAT_CHANNEL_MATRIX = {
    "audio": ("transistor", "social"),
    "video": ("youtube", "social"),
    "slide-deck": ("ghl-site",),
    "report": ("ghl-site",),
    "infographic": ("ghl-site", "social"),
    "mind-map": (),
    "quiz": (),
    "flashcards": (),
}

# Formats that stay in data/ and never fan out to a channel.
LOCAL_SCRATCH_FORMATS = ("mind-map", "quiz", "flashcards")

PUBLISH_CHANNELS = ("transistor", "youtube", "ghl-site", "social")

CHANNELS = {
    "transistor": {
        "status": "live",
        "owns": "Spotify / Apple / Amazon via Transistor.fm",
        "formats": ("audio",),
        "auth": ("TRANSISTOR_API_KEY", "TRANSISTOR_SHOW_ID"),
        "notes": "Draft then PATCH /publish. Dedupe against show episodes first.",
    },
    "youtube": {
        "status": "live",
        "owns": "YouTube long-form + Shorts (@williamcourterwelch)",
        "formats": ("video",),
        "auth": ("YOUTUBE_CLIENT_SECRETS", "YOUTUBE_TOKEN"),
        "notes": (
            "videos.insert via googleapiclient. Paths only — never bake secrets. "
            "YOUTUBE_PRIVACY=unlisted|public (default unlisted). Refresh via "
            "google.oauth2.credentials + Request."
        ),
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
}


def channels_for_format(fmt: str) -> tuple[str, ...]:
    """Audience channels for a Studio format. Empty = local scratch only."""
    return FORMAT_CHANNEL_MATRIX.get(fmt, ())


def is_local_scratch(fmt: str) -> bool:
    return not channels_for_format(fmt)


def required_auth(channel: str) -> tuple[str, ...]:
    info = CHANNELS.get(channel) or {}
    return tuple(info.get("auth") or ())
