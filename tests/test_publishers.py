import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.publishers import (
    publish_artifacts,
    publish_drive,
    publish_social,
    publish_transistor,
    publish_youtube,
)
from scripts.upload import content_type_for_audio, resolve_audio_url


class UploadHelpersTests(unittest.TestCase):
    def test_audio_url_preferred_over_content_url(self):
        self.assertEqual(
            resolve_audio_url({"audio_url": "https://cdn.example/a.m4a", "content_url": "old"}),
            "https://cdn.example/a.m4a",
        )

    def test_content_url_fallback(self):
        self.assertEqual(resolve_audio_url({"content_url": "https://cdn.example/a.mp3"}), "https://cdn.example/a.mp3")

    def test_missing_audio_url_raises(self):
        with self.assertRaises(KeyError) as ctx:
            resolve_audio_url({"upload_url": "https://s3"})
        self.assertIn("audio_url", str(ctx.exception))

    def test_m4a_content_type(self):
        self.assertEqual(content_type_for_audio("ep.m4a"), "audio/mp4")
        self.assertEqual(content_type_for_audio("ep.mp3"), "audio/mpeg")


class PublisherSkipTests(unittest.TestCase):
    def test_transistor_skips_without_keys(self):
        with tempfile.NamedTemporaryFile(suffix=".m4a") as f:
            with mock.patch.dict(os.environ, {}, clear=True):
                result = publish_transistor(f.name, "Title")
        self.assertEqual(result["status"], "skipped")
        self.assertIn("TRANSISTOR_API_KEY", result["reason"])

    def test_youtube_skips_without_creds(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            f.write(b"mp4")
            f.flush()
            result = publish_youtube(f.name, "Title")
        self.assertEqual(result["channel"], "youtube")
        self.assertEqual(result["status"], "skipped")
        self.assertIn("TODO", result["reason"])

    def test_drive_and_social_skip_without_creds(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            f.write(b"png")
            f.flush()
            with mock.patch.dict(os.environ, {}, clear=True):
                drive = publish_drive(f.name, "Title")
                social = publish_social(f.name, "Title")
        self.assertEqual(drive["status"], "skipped")
        self.assertEqual(social["status"], "skipped")
        self.assertIn("GOOGLE_DRIVE_FOLDER_ID", drive["reason"])
        self.assertIn("TODO", social["reason"])

    def test_thin_site_blocks_publish_bundle(self):
        results = publish_artifacts(
            [{"format": "audio", "path": "/tmp/x.m4a"}],
            {"title": "x", "publish_url": "https://globalhighlevel.com/new-page"},
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "blocked")
        self.assertIn("globalhighlevel.com", results[0]["reason"])

    def test_does_not_invent_tokens_when_files_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "video.mp4"
            fake.write_bytes(b"mp4")
            env = {
                "YOUTUBE_CLIENT_SECRETS": str(Path(tmp) / "no-such-secrets.json"),
                "YOUTUBE_TOKEN": str(Path(tmp) / "no-such-token.json"),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                result = publish_youtube(str(fake), "Demo")
            self.assertEqual(result["status"], "skipped")
            self.assertNotIn("AIza", result["reason"])
            self.assertNotIn("sk-", result["reason"])


class SeoModelFileTests(unittest.TestCase):
    def test_reads_anthropic_model_file(self):
        from scripts.seo import resolve_anthropic_model

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".anthropic_model"
            path.write_text("claude-haiku-4-5-20251001\n", encoding="utf-8")
            self.assertEqual(resolve_anthropic_model(tmp), "claude-haiku-4-5-20251001")


class CliHelpTests(unittest.TestCase):
    def test_help_lists_ai_lane_flags(self):
        from run import build_parser

        help_text = build_parser().format_help()
        self.assertIn("--ai-lane", help_text)
        self.assertIn("--formats", help_text)
        self.assertIn("--dry-run", help_text)


if __name__ == "__main__":
    unittest.main()
