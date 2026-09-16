"""
Transistor.fm uploader — uploads audio and publishes episodes.

Canary 2026-09-16: authorize field is `audio_url` (not `content_url`);
create a draft without `status`, then PATCH /v1/episodes/{id}/publish.
"""

import os

import requests


def _authorize_upload(api_key, filename):
    """Get an authorized upload URL from Transistor."""
    resp = requests.get(
        "https://api.transistor.fm/v1/episodes/authorize_upload",
        params={"filename": filename},
        headers={"x-api-key": api_key},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["data"]["attributes"]


def resolve_audio_url(upload_data):
    """Transistor returns audio_url; older docs/code used content_url."""
    audio_url = upload_data.get("audio_url") or upload_data.get("content_url")
    if not audio_url:
        raise KeyError(f"authorize_upload missing audio_url; keys={list(upload_data)}")
    return audio_url


def _upload_audio(upload_url, audio_path, content_type="audio/mpeg"):
    """Upload the audio file to the authorized URL."""
    with open(audio_path, "rb") as f:
        resp = requests.put(
            upload_url,
            data=f,
            headers={"Content-Type": content_type},
            timeout=300,
        )
        resp.raise_for_status()


def content_type_for_audio(filename):
    ext = os.path.splitext(filename)[1].lower()
    return {
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".mp4": "audio/mp4",
        ".wav": "audio/wav",
        ".aac": "audio/aac",
    }.get(ext, "audio/mpeg")


def upload_episode(audio_path, title, description="", tags=None, transcript=""):
    """
    Upload an episode to Transistor.fm.

    Args:
        audio_path: path to the audio file
        title: episode title
        description: episode description (HTML ok)
        tags: list of tag strings
        transcript: episode transcript text

    Returns:
        dict with 'id', 'share_url' keys
    """
    api_key = os.getenv("TRANSISTOR_API_KEY")
    show_id = os.getenv("TRANSISTOR_SHOW_ID")

    if not api_key or not show_id:
        raise ValueError("TRANSISTOR_API_KEY and TRANSISTOR_SHOW_ID required in .env")

    filename = os.path.basename(audio_path)
    content_type = content_type_for_audio(filename)

    # Step 1: Get authorized upload URL
    upload_data = _authorize_upload(api_key, filename)
    upload_url = upload_data["upload_url"]
    audio_url = resolve_audio_url(upload_data)

    # Step 2: Upload the audio
    _upload_audio(upload_url, audio_path, content_type=content_type)

    # Step 3: Create draft episode (status is NOT accepted on create)
    episode_data = {
        "episode": {
            "show_id": int(show_id),
            "title": title,
            "summary": description,
            "audio_url": audio_url,
        }
    }

    if tags:
        # Transistor uses keywords, not tags
        episode_data["episode"]["keywords"] = ", ".join(tags)

    if transcript:
        episode_data["episode"]["transcript_text"] = transcript

    resp = requests.post(
        "https://api.transistor.fm/v1/episodes",
        json=episode_data,
        headers={"x-api-key": api_key},
        timeout=30,
    )
    resp.raise_for_status()

    ep = resp.json()["data"]
    episode_id = ep["id"]

    # Step 4: Publish via dedicated endpoint
    pub = requests.patch(
        f"https://api.transistor.fm/v1/episodes/{episode_id}/publish",
        json={"episode": {"status": "published"}},
        headers={"x-api-key": api_key},
        timeout=30,
    )
    pub.raise_for_status()
    ep = pub.json()["data"]

    return {
        "id": ep["id"],
        "share_url": ep.get("attributes", {}).get("share_url", ""),
        "embed_html": ep.get("attributes", {}).get("embed_html", ""),
        "status": ep.get("attributes", {}).get("status", ""),
    }
