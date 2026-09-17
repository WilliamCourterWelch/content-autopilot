"""
Studio format parsing for the GHL AI multi-format lane.

Canonical names match `notebooklm generate <type>` in notebooklm-py 0.8:
audio, video, slide-deck, report, infographic, mind-map, quiz, flashcards.
"""

from __future__ import annotations

from typing import Iterable

STUDIO_FORMATS = (
    "audio",
    "video",
    "slide-deck",
    "report",
    "infographic",
    "mind-map",
    "quiz",
    "flashcards",
)

# CLI / human aliases → canonical `notebooklm generate <type>` name
FORMAT_ALIASES = {
    "audio": "audio",
    "podcast": "audio",
    "video": "video",
    "cinematic-video": "video",
    "cinematic_video": "video",
    "cinematicvideo": "video",
    "slide-deck": "slide-deck",
    "slide_deck": "slide-deck",
    "slidedeck": "slide-deck",
    "slides": "slide-deck",
    "deck": "slide-deck",
    "report": "report",
    "briefing": "report",
    "infographic": "infographic",
    "mind-map": "mind-map",
    "mind_map": "mind-map",
    "mindmap": "mind-map",
    "quiz": "quiz",
    "flashcards": "flashcards",
    "flash-cards": "flashcards",
    "flash_cards": "flashcards",
    "cards": "flashcards",
}

# Default canary: one audio overview, no volume blast.
DEFAULT_AI_LANE_FORMATS = ("audio",)

# Where artifacts land under data/
FORMAT_OUTPUT = {
    "audio": {"subdir": "audio", "ext": ".m4a", "cli": "audio"},
    "video": {"subdir": "video", "ext": ".mp4", "cli": "video"},
    "slide-deck": {"subdir": "slides", "ext": ".pdf", "cli": "slide-deck"},
    "report": {"subdir": "reports", "ext": ".md", "cli": "report"},
    "infographic": {"subdir": "infographics", "ext": ".png", "cli": "infographic"},
    "mind-map": {"subdir": "mindmaps", "ext": ".json", "cli": "mind-map"},
    "quiz": {"subdir": "quizzes", "ext": ".json", "cli": "quiz"},
    "flashcards": {"subdir": "flashcards", "ext": ".json", "cli": "flashcards"},
}

# notebooklm-py 0.8 ArtifactsAPI method names
FORMAT_API = {
    "audio": {"generate": "generate_audio", "download": "download_audio"},
    "video": {"generate": "generate_video", "download": "download_video"},
    "slide-deck": {"generate": "generate_slide_deck", "download": "download_slide_deck"},
    "report": {"generate": "generate_report", "download": "download_report"},
    "infographic": {"generate": "generate_infographic", "download": "download_infographic"},
    "mind-map": {"generate": "generate_mind_map", "download": "download_mind_map"},
    "quiz": {"generate": "generate_quiz", "download": "download_quiz"},
    "flashcards": {"generate": "generate_flashcards", "download": "download_flashcards"},
}


class UnknownFormatError(ValueError):
    """Raised when a requested Studio format is not in the 0.8 allowlist."""


def canonicalize_format(name: str) -> str:
    key = (name or "").strip().lower().replace(" ", "-")
    if key in ("all", "*"):
        raise UnknownFormatError(
            "'all' is not a single format; use parse_formats('all') to expand"
        )
    canonical = FORMAT_ALIASES.get(key)
    if not canonical:
        known = ", ".join(STUDIO_FORMATS)
        raise UnknownFormatError(f"Unknown Studio format {name!r}. Known: {known}")
    return canonical


def parse_formats(raw: str | Iterable[str] | None, default=DEFAULT_AI_LANE_FORMATS) -> list[str]:
    """
    Parse a comma-separated CLI string or iterable into canonical format names.

    Dedupes, preserves first-seen order. Empty / None → default (audio).
    `all` expands to every Studio type. Unknown names raise UnknownFormatError.
    """
    if raw is None:
        return list(default)

    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    else:
        parts = [str(p).strip() for p in raw]

    parts = [p for p in parts if p]
    if not parts:
        return list(default)

    if any(p.lower() in ("all", "*") for p in parts):
        return list(STUDIO_FORMATS)

    seen = set()
    out = []
    for part in parts:
        name = canonicalize_format(part)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def format_spec(name: str) -> dict:
    canonical = canonicalize_format(name)
    spec = dict(FORMAT_OUTPUT[canonical])
    spec.update(FORMAT_API[canonical])
    spec["name"] = canonical
    return spec
