import unittest
from datetime import datetime, timezone
from unittest import mock

from scripts.topic_picker import (
    SEED_AI_URLS,
    _article_href,
    _collect_links,
    hard_dedupe,
    money_adjacent_score,
    pick_topics,
    rank_money_adjacent,
)

CONVO = (
    "https://help.gohighlevel.com/support/solutions/articles/"
    "155000004401-how-to-set-up-a-conversation-ai-bot"
)
VOICE = (
    "https://help.gohighlevel.com/support/solutions/articles/"
    "155000007796-voice-ai-agent-transfer"
)
CHATBOT = (
    "https://help.gohighlevel.com/support/solutions/articles/"
    "155000000001-generic-chatbot-faq"
)
CHANGELOG_VOICE = "https://ideas.gohighlevel.com/changelog/voice-ai-agent-transfer-2026-09-01"


class CollectLinksTests(unittest.TestCase):
    def test_help_article_and_changelog_hrefs(self):
        self.assertTrue(
            _article_href(
                "/support/solutions/articles/155000004401-conversation-ai",
                "https://help.gohighlevel.com/support/search/solutions",
            )
        )
        self.assertTrue(_article_href("/changelog/voice-ai-agent-transfer", "https://ideas.gohighlevel.com/changelog"))
        self.assertIsNone(_article_href("/changelog", "https://ideas.gohighlevel.com/changelog"))
        self.assertIsNone(_article_href("/pricing", "https://www.gohighlevel.com"))

    def test_parses_mixed_listing_html(self):
        html = """
        <html><body>
          <a href="/support/solutions/articles/155000004401-conversation-ai">Conversation AI bot</a>
          <a href="/changelog/voice-ai-receptionist">Voice AI receptionist</a>
          <a href="/blog/unrelated">Skip</a>
        </body></html>
        """
        items = _collect_links(html, "https://help.gohighlevel.com/support/search/solutions")
        urls = [i["source_url"] for i in items]
        self.assertTrue(any("155000004401" in u for u in urls))
        # changelog relative to help host is not a changelog host
        ideas = _collect_links(html, "https://ideas.gohighlevel.com/changelog")
        self.assertTrue(any("voice-ai-receptionist" in i["source_url"] for i in ideas))


class RankTests(unittest.TestCase):
    def test_conversation_ai_beats_generic_chatbot(self):
        convo = {"source_url": CONVO, "title": "How to set up a Conversation AI bot", "snippet": ""}
        generic = {"source_url": CHATBOT, "title": "Generic chatbot FAQ", "snippet": "chatbot settings"}
        self.assertGreater(money_adjacent_score(convo), money_adjacent_score(generic))

    def test_voice_ai_booking_beats_old_help(self):
        money = {
            "source_url": CHANGELOG_VOICE,
            "title": "Voice AI receptionist books appointments",
            "snippet": "AI employee inbound missed calls Sep 1, 2026",
        }
        old = {
            "source_url": CHATBOT,
            "title": "Chatbot knowledge base",
            "snippet": "faq",
        }
        ranked = rank_money_adjacent([old, money], now=datetime(2026, 9, 16, tzinfo=timezone.utc))
        self.assertEqual(ranked[0]["source_url"], CHANGELOG_VOICE)

    def test_default_limit_is_one(self):
        candidates = [
            {"source_url": CHATBOT, "title": "Generic chatbot FAQ", "snippet": "chatbot settings"},
            {"source_url": CONVO, "title": "Conversation AI bot books appointments", "snippet": "inbound leads"},
        ]
        with mock.patch("scripts.topic_picker.collect_candidates", return_value=candidates):
            with mock.patch("scripts.topic_picker.hard_dedupe", side_effect=lambda items, **k: items):
                picked = pick_topics(limit=1, include_seeds=False)
        self.assertEqual(len(picked), 1)
        self.assertEqual(picked[0]["source_url"], CONVO)


class DedupePickerTests(unittest.TestCase):
    def test_drops_published_and_transistor_and_site(self):
        items = [
            {"source_url": CONVO, "title": "Conversation AI bot"},
            {"source_url": VOICE, "title": "Voice AI agent transfer"},
            {
                "source_url": "https://help.gohighlevel.com/support/solutions/articles/155000009999-ai-employee",
                "title": "AI employee inbound",
            },
        ]
        kept = hard_dedupe(
            items,
            published=[{"source": CONVO, "title": "old"}],
            transistor_episodes=[{"title": "Voice AI agent transfer", "source_url": ""}],
            site_slugs=["ai-employee-inbound"],
        )
        urls = [i["source_url"] for i in kept]
        self.assertNotIn(CONVO, urls)
        self.assertNotIn(VOICE, urls)
        self.assertEqual(kept, [])

    def test_keeps_new_money_topic(self):
        fresh = {
            "source_url": "https://help.gohighlevel.com/support/solutions/articles/155000008888-ai-receptionist",
            "title": "AI receptionist after hours",
        }
        kept = hard_dedupe(
            [fresh],
            published=[],
            transistor_episodes=[],
            site_slugs=[],
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["source_url"], fresh["source_url"])

    def test_seeds_are_ai_urls(self):
        self.assertGreaterEqual(len(SEED_AI_URLS), 3)
        from scripts.source_filter import classify_ghl_ai_source

        for url in SEED_AI_URLS:
            self.assertTrue(classify_ghl_ai_source(url).accepted)


if __name__ == "__main__":
    unittest.main()
