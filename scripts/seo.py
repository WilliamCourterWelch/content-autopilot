"""
SEO metadata writer — uses Claude to generate title, description, and tags.
"""

import json
import os
from pathlib import Path

# Spoken + written trial CTA. Always appended to YouTube and Transistor descriptions.
TRIAL_CTA_LINE = "Want a GoHighLevel 30-day free trial? Link in the description."


def resolve_affiliate_link():
    """Bootcamp / trial URL. AFFILIATE_LINK wins, then GHL_AFFILIATE_LINK. Never invent one."""
    return (os.getenv("AFFILIATE_LINK") or os.getenv("GHL_AFFILIATE_LINK") or "").strip()


def with_trial_cta(description: str, affiliate_url: str | None = None) -> str:
    """
    Ensure a distribution description includes the GHL trial CTA and affiliate URL.

    Idempotent: does not duplicate the CTA line or the link if already present.
    """
    desc = (description or "").strip()
    link = (affiliate_url if affiliate_url is not None else resolve_affiliate_link()).strip()
    parts = [desc] if desc else []
    if TRIAL_CTA_LINE.lower() not in desc.lower():
        parts.append(TRIAL_CTA_LINE)
    if link and link not in desc:
        parts.append(link)
    return "\n\n".join(parts)


def resolve_anthropic_model(base_dir=None):
    """Read the model name from `.anthropic_model`, then env, then default."""
    root = Path(base_dir) if base_dir else Path(__file__).parent.parent
    model_path = root / ".anthropic_model"
    if model_path.exists():
        model = model_path.read_text(encoding="utf-8").strip()
        if model:
            return model
    return os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


def write_seo(content, niche=""):
    """
    Generate SEO metadata for an episode.

    Args:
        content: dict with 'title' and 'body' keys
        niche: the podcast's niche/topic for context

    Returns:
        dict with 'title', 'description', 'tags' keys
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "title": content.get("title", ""),
            "description": with_trial_cta(content.get("body", "")[:200]),
            "tags": [],
        }

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    model = resolve_anthropic_model()

    podcast_name = os.getenv("PODCAST_NAME", "")
    affiliate_link = resolve_affiliate_link()

    prompt = f"""Write SEO metadata for a podcast episode.

Podcast: {podcast_name}
Niche: {niche}
Original title: {content.get('title', '')}

Article content (first 2000 chars):
{content.get('body', '')[:2000]}

Return a JSON object with:
- "title": A compelling podcast episode title (50-70 chars). Don't start with "How to" every time.
- "description": Episode description for podcast apps (150-250 chars). Make people want to listen.
- "tags": Array of 5-8 relevant tags/keywords.

{"Include this link in the description: " + affiliate_link if affiliate_link else ""}

Return ONLY valid JSON, no markdown fences."""

    response = client.messages.create(
        model=model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()

    # Parse JSON from response
    try:
        # Handle markdown fences if present
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            raise json.JSONDecodeError("expected object", text, 0)
        data["description"] = with_trial_cta(data.get("description") or "")
        return data
    except json.JSONDecodeError:
        return {
            "title": content.get("title", ""),
            "description": with_trial_cta(content.get("body", "")[:200]),
            "tags": [],
        }
