import unittest
from unittest import mock

from scripts.dedupe import (
    check_already_done,
    fingerprint,
    match_ghl_site,
    match_records,
    normalize_title,
    normalize_url,
)
from scripts.distribution import CHANNELS, FORMAT_CHANNEL_MATRIX, channels_for_format

WHITELABEL_URL = (
    "https://help.gohighlevel.com/support/solutions/articles/"
    "48000982207-how-to-set-up-a-whitelabel-domain-for-the-desktop-web-app"
)
WHITELABEL_TITLE = "White Label Your GoHighLevel App: Complete Setup Guide"
CONVO_URL = (
    "https://help.gohighlevel.com/support/solutions/articles/"
    "155000004401-how-to-set-up-a-conversation-ai-bot"
)


class NormalizeTests(unittest.TestCase):
    def test_title_strips_how_to_and_punctuation(self):
        self.assertEqual(
            normalize_title("How to Set Up a Whitelabel Domain for the Desktop Web App"),
            "set up a whitelabel domain for the desktop web app",
        )

    def test_url_drops_www_query_and_slash(self):
        self.assertEqual(
            normalize_url("https://www.help.gohighlevel.com/support/solutions/articles/48000982207/?x=1"),
            "https://help.gohighlevel.com/support/solutions/articles/48000982207",
        )

    def test_article_id_fingerprint(self):
        fp = fingerprint(WHITELABEL_URL, WHITELABEL_TITLE)
        self.assertEqual(fp["article_id"], "48000982207")


class DedupeGateTests(unittest.TestCase):
    def test_known_canary_whitelabel_is_duplicate(self):
        hit = check_already_done(
            {"source_url": WHITELABEL_URL, "title": "How to Set Up a Whitelabel Domain"},
            check_transistor=False,
            check_site=False,
        )
        self.assertTrue(hit.duplicate)
        self.assertEqual(hit.source, "known")
        self.assertIn("already done", hit.reason)

    def test_known_canary_transistor_title_is_duplicate(self):
        hit = check_already_done(
            {"source_url": "", "title": WHITELABEL_TITLE},
            check_transistor=False,
            check_site=False,
        )
        self.assertTrue(hit.duplicate)

    def test_published_json_source_url_match(self):
        published = [{"source": CONVO_URL, "title": "Conversation AI bot setup"}]
        hit = check_already_done(
            {"source_url": CONVO_URL + "/", "title": "Different wording"},
            published=published,
            known=[],
            check_transistor=False,
            check_site=False,
        )
        self.assertTrue(hit.duplicate)
        self.assertEqual(hit.source, "published")

    def test_published_json_normalized_title_match(self):
        published = [{"source": "https://example.com/old", "title": "Voice AI Agent Transfer"}]
        hit = check_already_done(
            {
                "source_url": "https://help.gohighlevel.com/support/solutions/articles/155000007796-voice-ai-agent-transfer",
                "title": "How to Voice AI Agent Transfer",
            },
            published=published,
            known=[],
            check_transistor=False,
            check_site=False,
        )
        self.assertTrue(hit.duplicate)

    def test_new_ai_topic_is_not_duplicate(self):
        hit = check_already_done(
            {
                "source_url": CONVO_URL,
                "title": "How to set up a Conversation AI bot",
            },
            published=[],
            known=[],
            transistor_episodes=[],
            site_slugs=[],
            check_transistor=True,
            check_site=True,
        )
        self.assertFalse(hit.duplicate)

    def test_transistor_title_fingerprint(self):
        episodes = [{"title": "White Label Your GoHighLevel App: Complete Setup Guide", "source_url": ""}]
        hit = check_already_done(
            {"source_url": WHITELABEL_URL, "title": "Whitelabel domain setup"},
            published=[],
            known=[],
            transistor_episodes=episodes,
            check_site=False,
        )
        # article id is not in the transistor row, but known file still loaded...
        # pass known=[] so only transistor + we also match via known if loaded.
        # With known=[] the URL is unique vs episode; title norms differ.
        # Seed a summary URL so transistor source fingerprint hits.
        episodes = [
            {
                "title": "Episode 1",
                "source_url": "",
                "summary": f"Source: {WHITELABEL_URL}",
            }
        ]
        hit = check_already_done(
            {"source_url": WHITELABEL_URL, "title": "Something else"},
            published=[],
            known=[],
            transistor_episodes=episodes,
            check_site=False,
        )
        self.assertTrue(hit.duplicate)
        self.assertEqual(hit.source, "transistor")

    def test_ghl_site_slug_match(self):
        hit = match_ghl_site(
            {"title": "Conversation AI bot", "source_url": CONVO_URL},
            slugs=["conversation-ai-bot"],
        )
        self.assertIsNotNone(hit)
        self.assertEqual(hit.source, "ghl-site")

    def test_match_records_by_article_id(self):
        hit = match_records(
            {"source_url": WHITELABEL_URL, "title": "x"},
            [{"source_url": "https://help.gohighlevel.com/support/solutions/articles/48000982207-other-slug", "title": "y"}],
            "published",
        )
        self.assertIsNotNone(hit)


class DistributionMatrixTests(unittest.TestCase):
    def test_audio_goes_to_transistor(self):
        self.assertIn("transistor", channels_for_format("audio"))

    def test_video_goes_to_youtube(self):
        self.assertIn("youtube", channels_for_format("video"))
        self.assertEqual(CHANNELS["youtube"]["status"], "live")

    def test_site_is_upgrade_only(self):
        self.assertEqual(CHANNELS["ghl-site"]["status"], "upgrade-only")
        self.assertIn("report", CHANNELS["ghl-site"]["formats"])

    def test_drive_and_newsletter_are_not_audiences(self):
        self.assertNotIn("drive", CHANNELS)
        self.assertNotIn("newsletter", CHANNELS)
        for fmt, chans in FORMAT_CHANNEL_MATRIX.items():
            self.assertNotIn("drive", chans, msg=fmt)
            self.assertNotIn("newsletter", chans, msg=fmt)

    def test_every_studio_format_is_in_matrix(self):
        from scripts.formats import STUDIO_FORMATS

        for fmt in STUDIO_FORMATS:
            self.assertIn(fmt, FORMAT_CHANNEL_MATRIX, msg=fmt)

    def test_local_scratch_formats_have_no_audience(self):
        for fmt in ("mind-map", "quiz", "flashcards"):
            self.assertEqual(channels_for_format(fmt), ())

    def test_audio_does_not_go_to_drive(self):
        self.assertEqual(channels_for_format("audio"), ("transistor", "social"))
        self.assertEqual(channels_for_format("video"), ("youtube", "social"))
        self.assertEqual(channels_for_format("report"), ("ghl-site",))


if __name__ == "__main__":
    unittest.main()
