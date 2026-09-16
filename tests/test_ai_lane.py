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


if __name__ == "__main__":
    unittest.main()
