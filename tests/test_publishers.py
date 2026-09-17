import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.publishers import (
    YOUTUBE_DESC_MAX,
    YOUTUBE_TITLE_MAX,
    YOUTUBE_TOKEN_URI,
    YOUTUBE_UPLOAD_SCOPE,
    _insert_youtube_video,
    load_youtube_credentials,
    oauth_client_fields,
    publish_artifacts,
    publish_social,
    publish_transistor,
    publish_youtube,
    refresh_youtube_credentials,
    resolve_youtube_privacy,
    youtube_oauth_paths,
)
from scripts.seo import TRIAL_CTA_LINE
from scripts.upload import content_type_for_audio, resolve_audio_url, upload_episode


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
            with mock.patch.dict(os.environ, {"YOUTUBE_CLIENT_SECRETS": "", "YOUTUBE_TOKEN": ""}, clear=False):
                result = publish_youtube(f.name, "Title")
        self.assertEqual(result["channel"], "youtube")
        self.assertEqual(result["status"], "skipped")
        self.assertIn("YOUTUBE_CLIENT_SECRETS", result["reason"])
        self.assertNotIn("TODO", result["reason"])

    def test_social_skips_without_creds(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            f.write(b"png")
            f.flush()
            with mock.patch.dict(os.environ, {}, clear=True):
                social = publish_social(f.name, "Title")
        self.assertEqual(social["status"], "skipped")
        self.assertIn("TODO", social["reason"])

    def test_drive_is_not_a_publish_destination(self):
        from scripts import publishers
        from scripts.distribution import CHANNELS, FORMAT_CHANNEL_MATRIX

        self.assertFalse(hasattr(publishers, "publish_drive"))
        self.assertNotIn("drive", CHANNELS)
        for fmt, chans in FORMAT_CHANNEL_MATRIX.items():
            self.assertNotIn("drive", chans, msg=fmt)
        self.assertEqual(CHANNELS["youtube"]["status"], "live")
        self.assertIn("youtube", FORMAT_CHANNEL_MATRIX["video"])

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


class YoutubePublisherTests(unittest.TestCase):
    def _write_oauth_files(self, tmp):
        secrets = Path(tmp) / "youtube-oauth-client.json"
        token = Path(tmp) / "youtube-oauth-token.json"
        secrets.write_text(
            json.dumps(
                {
                    "installed": {
                        "client_id": "test-client-id.apps.googleusercontent.com",
                        "client_secret": "test-client-secret",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                }
            ),
            encoding="utf-8",
        )
        token.write_text(
            json.dumps(
                {
                    "token": "ya29.test-access-token",
                    "refresh_token": "1//test-refresh-token",
                    "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
                }
            ),
            encoding="utf-8",
        )
        return secrets, token

    def test_privacy_defaults_unlisted(self):
        with mock.patch.dict(os.environ, {"YOUTUBE_PRIVACY": ""}, clear=False):
            self.assertEqual(resolve_youtube_privacy(), "unlisted")
        with mock.patch.dict(os.environ, {"YOUTUBE_PRIVACY": "public"}, clear=False):
            self.assertEqual(resolve_youtube_privacy(), "public")
        self.assertEqual(resolve_youtube_privacy("PRIVATE"), "unlisted")

    def test_oauth_client_fields_merge_secrets_and_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            secrets, token = self._write_oauth_files(tmp)
            fields = oauth_client_fields(str(secrets), str(token))
        self.assertEqual(fields["client_id"], "test-client-id.apps.googleusercontent.com")
        self.assertEqual(fields["refresh_token"], "1//test-refresh-token")
        self.assertEqual(fields["token_uri"], "https://oauth2.googleapis.com/token")

    def test_refresh_when_expired(self):
        creds = mock.Mock()
        creds.refresh_token = "1//test-refresh-token"
        creds.valid = False
        creds.expired = True
        request = mock.Mock()
        self.assertTrue(refresh_youtube_credentials(creds, request_factory=lambda: request))
        creds.refresh.assert_called_once_with(request)

    def test_refresh_skipped_when_valid(self):
        creds = mock.Mock()
        creds.refresh_token = "1//test-refresh-token"
        creds.valid = True
        creds.expired = False
        self.assertFalse(refresh_youtube_credentials(creds, request_factory=mock.Mock))
        creds.refresh.assert_not_called()

    def test_mocked_videos_insert_publishes_unlisted_with_cta(self):
        with tempfile.TemporaryDirectory() as tmp:
            secrets, token = self._write_oauth_files(tmp)
            video = Path(tmp) / "demo.mp4"
            video.write_bytes(b"mp4-bytes")
            env = {
                "YOUTUBE_CLIENT_SECRETS": str(secrets),
                "YOUTUBE_TOKEN": str(token),
                "YOUTUBE_PRIVACY": "unlisted",
                "AFFILIATE_LINK": "https://example.com/ghl-bootcamp",
            }
            insert = mock.Mock(return_value={"id": "vidTEST123"})
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch("scripts.publishers.load_youtube_credentials", return_value="creds") as load:
                    with mock.patch("scripts.publishers._insert_youtube_video", insert):
                        result = publish_youtube(str(video), "Conversation AI setup", "Walkthrough of the bot.")
            load.assert_called_once_with(str(secrets), str(token))
            insert.assert_called_once()
            args, kwargs = insert.call_args
            self.assertEqual(args[0], "creds")
            self.assertEqual(args[1], str(video))
            self.assertEqual(args[2], "Conversation AI setup")
            self.assertIn(TRIAL_CTA_LINE, args[3])
            self.assertIn("https://example.com/ghl-bootcamp", args[3])
            self.assertEqual(args[4], "unlisted")
            self.assertEqual(result["status"], "published")
            self.assertEqual(result["id"], "vidTEST123")
            self.assertEqual(result["url"], "https://www.youtube.com/watch?v=vidTEST123")
            self.assertEqual(result["privacy"], "unlisted")
            self.assertNotIn("test-client-secret", result["reason"])

    def test_mocked_insert_respects_public_privacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            secrets, token = self._write_oauth_files(tmp)
            video = Path(tmp) / "demo.mp4"
            video.write_bytes(b"mp4-bytes")
            env = {
                "YOUTUBE_CLIENT_SECRETS": str(secrets),
                "YOUTUBE_TOKEN": str(token),
                "YOUTUBE_PRIVACY": "public",
                "AFFILIATE_LINK": "",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch("scripts.publishers.load_youtube_credentials", return_value="creds"):
                    with mock.patch(
                        "scripts.publishers._insert_youtube_video",
                        return_value={"id": "pub1"},
                    ) as insert:
                        result = publish_youtube(str(video), "Title", "Desc")
            self.assertEqual(insert.call_args[0][4], "public")
            self.assertEqual(result["privacy"], "public")

    def test_publish_artifacts_video_calls_youtube(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"mp4")
            with mock.patch(
                "scripts.publishers.publish_youtube",
                return_value={"channel": "youtube", "status": "published", "reason": "ok"},
            ) as yt:
                results = publish_artifacts(
                    [{"format": "video", "path": str(video)}],
                    {"title": "Voice AI"},
                    seo_data={"title": "Voice AI", "description": "How Voice AI answers the phone."},
                )
            yt.assert_called_once()
            self.assertEqual(yt.call_args[0][0], str(video))
            self.assertTrue(any(r["channel"] == "youtube" for r in results))

    def test_transistor_description_gets_cta(self):
        with tempfile.NamedTemporaryFile(suffix=".m4a") as f:
            f.write(b"m4a")
            f.flush()
            env = {
                "TRANSISTOR_API_KEY": "test-key",
                "TRANSISTOR_SHOW_ID": "1",
                "AFFILIATE_LINK": "https://example.com/aff",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch(
                    "scripts.upload.upload_episode",
                    return_value={"status": "published", "share_url": "https://share.example/x", "id": "ep1"},
                ) as upload:
                    result = publish_transistor(f.name, "Title", description="Audio walkthrough.")
            self.assertEqual(result["status"], "published")
            sent = upload.call_args.kwargs["description"]
            self.assertIn(TRIAL_CTA_LINE, sent)
            self.assertIn("https://example.com/aff", sent)

    def test_skips_when_video_missing(self):
        self.assertEqual(publish_youtube(None, "Title")["status"], "skipped")
        self.assertEqual(publish_youtube("", "Title")["reason"], "no local video artifact")
        missing = publish_youtube("/tmp/does-not-exist-youtube.mp4", "Title")
        self.assertEqual(missing["status"], "skipped")
        self.assertIn("no local video artifact", missing["reason"])

    def test_insert_exception_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            secrets, token = self._write_oauth_files(tmp)
            video = Path(tmp) / "demo.mp4"
            video.write_bytes(b"mp4")
            env = {
                "YOUTUBE_CLIENT_SECRETS": str(secrets),
                "YOUTUBE_TOKEN": str(token),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch("scripts.publishers.load_youtube_credentials", return_value="creds"):
                    with mock.patch(
                        "scripts.publishers._insert_youtube_video",
                        side_effect=RuntimeError("quotaExceeded"),
                    ):
                        result = publish_youtube(str(video), "Title", "Desc")
        self.assertEqual(result["status"], "error")
        self.assertIn("RuntimeError", result["reason"])
        self.assertIn("quotaExceeded", result["reason"])
        self.assertNotIn("test-client-secret", result["reason"])

    def test_error_reason_redacts_token_shaped_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            secrets, token = self._write_oauth_files(tmp)
            video = Path(tmp) / "demo.mp4"
            video.write_bytes(b"mp4")
            env = {
                "YOUTUBE_CLIENT_SECRETS": str(secrets),
                "YOUTUBE_TOKEN": str(token),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch("scripts.publishers.load_youtube_credentials", return_value="creds"):
                    with mock.patch(
                        "scripts.publishers._insert_youtube_video",
                        side_effect=RuntimeError("refresh_token=1//leaked-refresh ya29.leaked-access"),
                    ):
                        result = publish_youtube(str(video), "Title", "Desc")
        self.assertEqual(result["status"], "error")
        self.assertNotIn("1//leaked-refresh", result["reason"])
        self.assertNotIn("ya29.leaked-access", result["reason"])
        self.assertIn("[redacted]", result["reason"])

    def test_published_without_video_id_has_empty_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            secrets, token = self._write_oauth_files(tmp)
            video = Path(tmp) / "demo.mp4"
            video.write_bytes(b"mp4")
            env = {
                "YOUTUBE_CLIENT_SECRETS": str(secrets),
                "YOUTUBE_TOKEN": str(token),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch("scripts.publishers.load_youtube_credentials", return_value="creds"):
                    with mock.patch("scripts.publishers._insert_youtube_video", return_value=None):
                        result = publish_youtube(str(video), "Title", "Desc")
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["id"], "")
        self.assertEqual(result["url"], "")

    def test_publish_artifacts_cinematic_video_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "cine.mp4"
            video.write_bytes(b"mp4")
            with mock.patch(
                "scripts.publishers.publish_youtube",
                return_value={"channel": "youtube", "status": "published", "reason": "ok"},
            ) as yt:
                results = publish_artifacts(
                    [{"format": "cinematic-video", "path": str(video)}],
                    {"title": "Voice AI"},
                    seo_data={"title": "Voice AI", "description": "Cinematic cut."},
                    channels=["youtube"],
                )
            yt.assert_called_once()
            self.assertEqual(yt.call_args[0][0], str(video))
            self.assertTrue(any(r["channel"] == "youtube" for r in results))

    def test_oauth_web_client_access_token_and_string_scopes(self):
        with tempfile.TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "web.json"
            token = Path(tmp) / "token.json"
            secrets.write_text(
                json.dumps(
                    {
                        "web": {
                            "client_id": "web-client.apps.googleusercontent.com",
                            "client_secret": "web-secret",
                        }
                    }
                ),
                encoding="utf-8",
            )
            token.write_text(
                json.dumps(
                    {
                        "access_token": "ya29.from-access-token",
                        "refresh_token": "1//refresh",
                        "scopes": YOUTUBE_UPLOAD_SCOPE,
                    }
                ),
                encoding="utf-8",
            )
            fields = oauth_client_fields(str(secrets), str(token))
        self.assertEqual(fields["client_id"], "web-client.apps.googleusercontent.com")
        self.assertEqual(fields["token"], "ya29.from-access-token")
        self.assertEqual(fields["scopes"], [YOUTUBE_UPLOAD_SCOPE])
        self.assertEqual(fields["token_uri"], YOUTUBE_TOKEN_URI)

    def test_oauth_non_object_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "s.json"
            token = Path(tmp) / "t.json"
            secrets.write_text("[]", encoding="utf-8")
            token.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                oauth_client_fields(str(secrets), str(token))
            secrets.write_text(json.dumps({"installed": "not-an-object"}), encoding="utf-8")
            token.write_text(json.dumps({"refresh_token": "x"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                oauth_client_fields(str(secrets), str(token))

    def test_load_credentials_requires_client_id_and_refresh(self):
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "s.json"
            token = Path(tmp) / "t.json"
            secrets.write_text(json.dumps({"installed": {"client_secret": "only-secret"}}), encoding="utf-8")
            token.write_text(json.dumps({"token": "ya29.x"}), encoding="utf-8")
            creds_mod = mock.Mock()
            with mock.patch.dict(sys.modules, {"google.oauth2.credentials": creds_mod}):
                with self.assertRaises(ValueError) as ctx:
                    load_youtube_credentials(str(secrets), str(token))
        creds_mod.Credentials.assert_not_called()
        self.assertIn("client_id", str(ctx.exception))
        self.assertIn("refresh_token", str(ctx.exception))

    def test_load_credentials_skips_write_when_not_refreshed(self):
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            secrets, token = self._write_oauth_files(tmp)
            before = token.read_text(encoding="utf-8")
            creds = mock.Mock()
            creds_mod = mock.Mock()
            creds_mod.Credentials.return_value = creds
            with mock.patch.dict(sys.modules, {"google.oauth2.credentials": creds_mod}):
                with mock.patch("scripts.publishers.refresh_youtube_credentials", return_value=False):
                    out = load_youtube_credentials(str(secrets), str(token))
            self.assertIs(out, creds)
            self.assertEqual(token.read_text(encoding="utf-8"), before)
            creds.to_json.assert_not_called()

    def test_refresh_default_factory_uses_google_request(self):
        import sys

        creds = mock.Mock()
        creds.refresh_token = "1//test-refresh-token"
        creds.valid = False
        creds.expired = True
        request_obj = mock.Mock()
        transport = mock.Mock()
        transport.Request.return_value = request_obj
        with mock.patch.dict(sys.modules, {"google.auth.transport.requests": transport}):
            self.assertTrue(refresh_youtube_credentials(creds))
        transport.Request.assert_called_once_with()
        creds.refresh.assert_called_once_with(request_obj)

    def test_load_credentials_persists_refreshed_token(self):
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            secrets, token = self._write_oauth_files(tmp)
            creds = mock.Mock()
            creds.to_json.return_value = json.dumps({"token": "ya29.refreshed"})
            creds_mod = mock.Mock()
            creds_mod.Credentials.return_value = creds
            with mock.patch.dict(sys.modules, {"google.oauth2.credentials": creds_mod}):
                with mock.patch("scripts.publishers.refresh_youtube_credentials", return_value=True):
                    out = load_youtube_credentials(str(secrets), str(token))
            self.assertIs(out, creds)
            self.assertEqual(json.loads(token.read_text(encoding="utf-8"))["token"], "ya29.refreshed")
            self.assertEqual(stat.S_IMODE(token.stat().st_mode), 0o600)

    def test_youtube_oauth_paths_credentials_alias(self):
        env = {
            "YOUTUBE_CLIENT_SECRETS": "",
            "YOUTUBE_CREDENTIALS": "/home/box/.secrets/youtube-oauth-client.json",
            "YOUTUBE_TOKEN": "/home/box/.secrets/youtube-oauth-token.json",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            secrets, token = youtube_oauth_paths()
        self.assertEqual(secrets, "/home/box/.secrets/youtube-oauth-client.json")
        self.assertEqual(token, "/home/box/.secrets/youtube-oauth-token.json")

    def test_refresh_skipped_without_refresh_token(self):
        creds = mock.Mock()
        creds.refresh_token = None
        creds.valid = False
        creds.expired = True
        self.assertFalse(refresh_youtube_credentials(creds, request_factory=mock.Mock))
        creds.refresh.assert_not_called()

    def test_insert_truncates_title_description_and_defaults_title(self):
        import sys

        youtube = mock.Mock()
        youtube.videos.return_value.insert.return_value.execute.return_value = {"id": "vid1"}
        discovery = mock.Mock()
        discovery.build.return_value = youtube
        http_mod = mock.Mock()
        http_mod.MediaFileUpload.return_value = "media"
        with mock.patch.dict(
            sys.modules,
            {"googleapiclient.discovery": discovery, "googleapiclient.http": http_mod},
        ):
            _insert_youtube_video("creds", "/tmp/v.mp4", "T" * 180, "D" * 6000, "unlisted")
            empty = _insert_youtube_video("creds", "/tmp/v.mp4", "", None, "public")
        self.assertEqual(empty, {"id": "vid1"})
        first_body = youtube.videos.return_value.insert.call_args_list[0].kwargs["body"]
        self.assertEqual(len(first_body["snippet"]["title"]), YOUTUBE_TITLE_MAX)
        self.assertEqual(len(first_body["snippet"]["description"]), YOUTUBE_DESC_MAX)
        self.assertEqual(first_body["status"]["privacyStatus"], "unlisted")
        second_body = youtube.videos.return_value.insert.call_args_list[1].kwargs["body"]
        self.assertEqual(second_body["snippet"]["title"], "GHL AI")
        self.assertEqual(second_body["snippet"]["description"], "")
        self.assertEqual(second_body["status"]["privacyStatus"], "public")
        http_mod.MediaFileUpload.assert_called_with("/tmp/v.mp4", mimetype="video/mp4", resumable=True)

    def test_upload_episode_applies_cta_before_create(self):
        auth = {"upload_url": "https://s3.example/up", "audio_url": "https://cdn.example/a.m4a"}
        create_resp = mock.Mock()
        create_resp.json.return_value = {"data": {"id": "ep1"}}
        pub_resp = mock.Mock()
        pub_resp.json.return_value = {
            "data": {
                "id": "ep1",
                "attributes": {"share_url": "https://share.example/x", "status": "published"},
            }
        }
        env = {
            "TRANSISTOR_API_KEY": "test-key",
            "TRANSISTOR_SHOW_ID": "9",
            "AFFILIATE_LINK": "https://example.com/aff",
        }
        with tempfile.NamedTemporaryFile(suffix=".m4a") as f:
            f.write(b"m4a")
            f.flush()
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch("scripts.upload._authorize_upload", return_value=auth):
                    with mock.patch("scripts.upload._upload_audio"):
                        with mock.patch("scripts.upload.requests.post", return_value=create_resp) as post:
                            with mock.patch("scripts.upload.requests.patch", return_value=pub_resp):
                                out = upload_episode(f.name, "Title", description="Audio walkthrough.")
        self.assertEqual(out["id"], "ep1")
        summary = post.call_args.kwargs["json"]["episode"]["summary"]
        self.assertIn("Audio walkthrough.", summary)
        self.assertIn(TRIAL_CTA_LINE, summary)
        self.assertIn("https://example.com/aff", summary)


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
