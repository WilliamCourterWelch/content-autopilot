import unittest

from scripts.source_filter import (
    classify_ghl_ai_source,
    filter_sources,
    is_ghl_ai_source,
    is_thin_site_destination,
)

CONVO = "https://help.gohighlevel.com/support/solutions/articles/155000004401-how-to-set-up-a-conversation-ai-bot"
VOICE = "https://help.gohighlevel.com/support/solutions/articles/155000007796-voice-ai-agent-transfer"
AGENTS = "https://help.gohighlevel.com/support/solutions/articles/155000005427-conversation-ai-agents-dashboard"
WHITELABEL = "https://help.gohighlevel.com/support/solutions/articles/48000982207-how-to-set-up-a-whitelabel-domain-for-the-desktop-web-app"
CHANGELOG_AI = "https://ideas.gohighlevel.com/changelog/voice-ai-agent-transfer"
RANDOM_BLOG = "https://example.com/blog/best-crm-tips"
THIN = "https://globalhighlevel.com/conversation-ai-guide"


class SourceFilterTests(unittest.TestCase):
    def test_accepts_conversation_ai_help_url(self):
        result = classify_ghl_ai_source(CONVO)
        self.assertTrue(result.accepted)
        self.assertEqual(result.kind, "ai-help")
        self.assertTrue(any("conversation" in m for m in result.matched))

    def test_accepts_voice_ai_and_agents(self):
        self.assertTrue(is_ghl_ai_source(VOICE))
        self.assertTrue(is_ghl_ai_source(AGENTS))

    def test_rejects_non_ai_help_article_by_default(self):
        result = classify_ghl_ai_source(
            WHITELABEL,
            title="White Label Your GoHighLevel App",
            body="Set up a custom domain for the desktop web app.",
        )
        self.assertFalse(result.accepted)
        self.assertIn("not a GHL AI", result.reason)

    def test_require_ai_false_allows_help_host(self):
        result = classify_ghl_ai_source(WHITELABEL, require_ai=False)
        self.assertTrue(result.accepted)

    def test_accepts_changelog_with_ai_slug(self):
        result = classify_ghl_ai_source(CHANGELOG_AI)
        self.assertTrue(result.accepted)
        self.assertEqual(result.kind, "ai-changelog")

    def test_rejects_random_domain(self):
        result = classify_ghl_ai_source(RANDOM_BLOG, title="Conversation AI tips")
        self.assertFalse(result.accepted)
        self.assertIn("not a GHL help", result.reason)

    def test_rejects_missing_url(self):
        result = classify_ghl_ai_source("")
        self.assertFalse(result.accepted)

    def test_thin_site_destination(self):
        self.assertTrue(is_thin_site_destination(THIN))
        self.assertTrue(is_thin_site_destination("https://www.globalhighlevel.com/x"))
        self.assertFalse(is_thin_site_destination(CONVO))
        result = classify_ghl_ai_source(THIN, title="Conversation AI")
        self.assertFalse(result.accepted)
        self.assertEqual(result.kind, "thin-site")
        self.assertIn("globalhighlevel.com", result.reason)

    def test_title_body_keywords_on_help_host(self):
        url = "https://help.gohighlevel.com/support/solutions/articles/155000099999-misc"
        result = classify_ghl_ai_source(url, title="Using an AI employee", body="")
        self.assertTrue(result.accepted)
        self.assertIn("ai employee", result.matched)

    def test_filter_sources_keeps_only_ai(self):
        items = [
            CONVO,
            WHITELABEL,
            {"url": VOICE, "title": "Voice AI agent transfer"},
            {"source_url": RANDOM_BLOG, "title": "Voice AI"},
        ]
        kept = filter_sources(items)
        urls = [k.get("source_url") or k.get("url") for k in kept]
        self.assertEqual(urls, [CONVO, VOICE])
        self.assertIn("matched", kept[0]["_ai_filter"])


if __name__ == "__main__":
    unittest.main()
