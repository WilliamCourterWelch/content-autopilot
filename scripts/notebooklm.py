"""
NotebookLM generator — podcast audio + Studio multi-format artifacts.

Uses notebooklm-py 0.8+ (NotebookLMClient async API + storage_state.json).
Studio types match `notebooklm generate <type>`: audio, video, slide-deck,
report, infographic, mind-map, quiz, flashcards.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from scripts.formats import format_spec, parse_formats

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
AUDIO_DIR = DATA_DIR / "audio"

GHL_AI_INSTRUCTIONS = (
    "Create a clear, practical how-to for GoHighLevel users covering the "
    "AI feature in the source (Conversation AI, Voice AI, or AI agents). "
    "Cover the steps in order, call out requirements and common pitfalls, "
    "and keep the tone helpful and professional. Do not invent product features."
)


def _resolve_storage_state() -> Path:
    """Prefer repo symlink/copy, then default NotebookLM profile."""
    candidates = [
        BASE_DIR / "storage_state.json",
        Path.home() / ".notebooklm" / "profiles" / "default" / "storage_state.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "NotebookLM not authenticated. Run: notebooklm login "
        "(expect storage_state.json in the repo or ~/.notebooklm/profiles/default/)"
    )


def _safe_stem(title: str) -> str:
    safe = "".join(c if c.isalnum() or c in " -_" else "" for c in (title or ""))[:80].strip()
    return safe or "episode"


async def _add_source(client, notebook_id: str, content: dict):
    title = content.get("title", "Untitled")
    body = content.get("body", "")
    source_url = (content.get("source_url") or "").strip()

    if source_url.startswith("http"):
        source = await client.sources.add_url(
            notebook_id,
            source_url,
            wait=False,
            title=title,
        )
    else:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(f"{title}\n\n{body}")
            source_path = f.name
        try:
            source = await client.sources.add_file(
                notebook_id,
                source_path,
                wait=False,
                title=title,
            )
        finally:
            try:
                os.unlink(source_path)
            except OSError:
                pass

    await client.sources.wait_until_ready(notebook_id, source.id, timeout=600)
    return source


async def _wait_artifact(client, notebook_id: str, task) -> None:
    task_id = getattr(task, "task_id", None) or getattr(task, "id", None)
    if not task_id:
        # mind-map generate_mind_map returns MindMapResult (already complete)
        return
    final = await client.artifacts.wait_for_completion(
        notebook_id,
        task_id,
        timeout=1200,
        # NotebookLM briefly drops artifacts from the list near completion;
        # default max_not_found=5 can false-fail a finished audio job.
        max_not_found=30,
        min_not_found_window=60.0,
    )
    if hasattr(final, "is_complete") and not final.is_complete:
        raise RuntimeError(f"Generation ended with {final.status}: {final.error}")


def _task_id(task) -> str | None:
    return getattr(task, "task_id", None) or getattr(task, "id", None) or getattr(
        task, "note_id", None
    )


async def _generate_one_format(client, notebook_id: str, source_id: str, fmt: str, dest: Path, instructions: str):
    spec = format_spec(fmt)
    artifacts = client.artifacts
    generate = getattr(artifacts, spec["generate"], None)
    download = getattr(artifacts, spec["download"], None)
    if generate is None or download is None:
        raise RuntimeError(
            f"notebooklm-py is missing {spec['generate']}/{spec['download']}. "
            f"Need 0.8+. CLI equivalent: notebooklm generate {spec['cli']}"
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {"source_ids": [source_id]}
    # Only pass kwargs the method accepts.
    import inspect

    params = inspect.signature(generate).parameters
    if "instructions" in params:
        kwargs["instructions"] = instructions
    if "language" in params:
        kwargs["language"] = "en"
    if "extra_instructions" in params and "instructions" not in params:
        kwargs["extra_instructions"] = instructions

    task = await generate(notebook_id, **kwargs)
    await _wait_artifact(client, notebook_id, task)
    artifact_id = _task_id(task)
    download_kwargs = {}
    if artifact_id:
        download_kwargs["artifact_id"] = artifact_id
    downloaded = await download(notebook_id, str(dest), **download_kwargs)
    return downloaded or str(dest)


async def _generate_audio_async(content: dict) -> dict:
    from notebooklm import NotebookLMClient

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    storage_state = _resolve_storage_state()
    title = content.get("title", "Untitled")
    audio_path = AUDIO_DIR / f"{_safe_stem(title)}.m4a"

    async with NotebookLMClient.from_storage(path=str(storage_state)) as client:
        notebook = await client.notebooks.create(f"Podcast: {title}"[:120])
        notebook_id = notebook.id
        try:
            source = await _add_source(client, notebook_id, content)
            task = await client.artifacts.generate_audio(
                notebook_id,
                source_ids=[source.id],
                language="en",
                instructions=GHL_AI_INSTRUCTIONS,
            )
            await _wait_artifact(client, notebook_id, task)
            downloaded = await client.artifacts.download_audio(
                notebook_id,
                str(audio_path),
                artifact_id=task.task_id,
            )
            return {"audio_path": downloaded or str(audio_path)}
        finally:
            try:
                await client.notebooks.delete(notebook_id)
            except Exception:
                pass


async def _generate_studio_async(content: dict, formats) -> dict:
    from notebooklm import NotebookLMClient

    storage_state = _resolve_storage_state()
    title = content.get("title", "Untitled")
    stem = _safe_stem(title)
    requested = parse_formats(formats)
    artifacts = []

    async with NotebookLMClient.from_storage(path=str(storage_state)) as client:
        notebook = await client.notebooks.create(f"GHL AI Studio: {title}"[:120])
        notebook_id = notebook.id
        try:
            source = await _add_source(client, notebook_id, content)
            for fmt in requested:
                spec = format_spec(fmt)
                dest = DATA_DIR / spec["subdir"] / f"{stem}{spec['ext']}"
                path = await _generate_one_format(
                    client, notebook_id, source.id, fmt, dest, GHL_AI_INSTRUCTIONS
                )
                artifacts.append(
                    {
                        "format": spec["name"],
                        "path": path,
                        "cli": f"notebooklm generate {spec['cli']}",
                    }
                )
        finally:
            try:
                await client.notebooks.delete(notebook_id)
            except Exception:
                pass

    audio = next((a["path"] for a in artifacts if a["format"] == "audio"), "")
    return {"artifacts": artifacts, "audio_path": audio, "notebook_deleted": True}


def generate_audio(content):
    """
    Generate podcast audio from content using NotebookLM.

    Args:
        content: dict with 'title' and 'body' keys (optional 'source_url')

    Returns:
        dict with 'audio_path' key
    """
    try:
        return asyncio.run(_generate_audio_async(content))
    except ImportError as e:
        raise ImportError(
            "notebooklm-py not installed. Run: pip install 'notebooklm-py>=0.8.0'"
        ) from e
    except Exception as e:
        raise RuntimeError(f"NotebookLM generation failed: {e}") from e


def generate_studio(content, formats=None):
    """
    Generate one or more Studio artifacts from a single GHL AI source.

    `formats` is a comma string or iterable of `notebooklm generate <type>` names.
    Artifacts download into data/<subdir>/.
    """
    try:
        return asyncio.run(_generate_studio_async(content, formats))
    except ImportError as e:
        raise ImportError(
            "notebooklm-py not installed. Run: pip install 'notebooklm-py>=0.8.0'"
        ) from e
    except Exception as e:
        raise RuntimeError(f"NotebookLM Studio generation failed: {e}") from e
