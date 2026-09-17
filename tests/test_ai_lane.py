import unittest
from unittest import mock

from scripts.ai_lane import SEED_AI_URLS, resolve_topics
from scripts.formats import parse_formats
from scripts.source_filter import classify_ghl_ai_source


class AiLaneCanaryTests(unittest.TestCase):
    def test_seeds_are_ai_help_articles(self):
        self.assertGreaterEqual(len(SEED_AI_URLS), 3)
        for url in SEED_AI_URLS:
            result = classify_ghl_ai_source(url)
            self.assertTrue(result.accepted, msg=f"{url} rejected: {result.reason}")

    def test_default_formats_match_cli_example_subset(self):
        example = parse_formats("audio,report,infographic")
        self.assertEqual(example, ["audio", "report", "infographic"])

    def test_resolve_url_rejects_non_ai(self):
        with mock.patch("scripts.ai_lane.scrape_article", return_value=None):
            with self.assertRaises(ValueError):
                resolve_topics(
                    url="https://help.gohighlevel.com/support/solutions/articles/48000982207-whitelabel-domain"
                )

    def test_resolve_url_accepts_conversation_ai(self):
        url = SEED_AI_URLS[0]
        fake = {
            "title": "How to set up a Conversation AI bot",
            "body": "Conversation AI setup steps.",
            "source_url": url,
            "source_type": "ghl-ai-help",
        }
        with mock.patch("scripts.ai_lane.scrape_article", return_value=fake):
            topics = resolve_topics(url=url, limit=1)
        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0]["source_url"], url)
        self.assertTrue(topics[0]["_ai_filter"]["matched"])

    def test_scrape_rejects_off_allowlist_redirect(self):
        class _Resp:
            url = "http://127.0.0.1/secret"
            text = "<html><h1>Conversation AI</h1><main>" + ("x" * 200) + "</main></html>"

            def raise_for_status(self):
                return None

        with mock.patch("scripts.ai_lane.requests.get", return_value=_Resp()):
            from scripts.ai_lane import scrape_article

            self.assertIsNone(
                scrape_article(
                    "https://help.gohighlevel.com/support/solutions/articles/155000004401-conversation-ai"
                )
            )

    def test_run_ai_lane_seo_includes_trial_cta(self):
        from scripts.ai_lane import run_ai_lane
        from scripts.seo import TRIAL_CTA_LINE

        content = {
            "title": "How to set up a Conversation AI bot",
            "body": "Conversation AI setup steps for Voice AI agents.",
            "source_url": SEED_AI_URLS[0],
            "source_type": "ghl-ai-help",
            "_ai_filter": {"matched": ["conversation ai"], "reason": "ok"},
        }
        env = {"ANTHROPIC_API_KEY": "", "AFFILIATE_LINK": "https://example.com/aff"}
        with mock.patch.dict("os.environ", env, clear=False):
            with mock.patch("scripts.ai_lane.resolve_topics", return_value=[content]):
                with mock.patch(
                    "scripts.ai_lane.check_already_done",
                    return_value=mock.Mock(duplicate=False, reason="ok"),
                ):
                    with mock.patch(
                        "scripts.notebooklm.generate_studio",
                        return_value={"artifacts": [{"format": "video", "path": "/tmp/v.mp4"}]},
                    ):
                        with mock.patch("scripts.ai_lane.publish_artifacts", return_value=[]) as pub:
                            with mock.patch("scripts.ai_lane.load_published", return_value=[]):
                                with mock.patch("scripts.ai_lane.save_published"):
                                    result = run_ai_lane(formats="video")
        self.assertTrue(result["ok"])
        seo = pub.call_args.kwargs["seo_data"]
        self.assertIn(TRIAL_CTA_LINE, seo["description"])
        self.assertIn("https://example.com/aff", seo["description"])
        self.assertIn("Conversation AI setup steps", seo["description"])


if __name__ == "__main__":
    unittest.main()
