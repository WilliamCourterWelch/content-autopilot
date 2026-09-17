import os
import unittest
from unittest import mock

from scripts.seo import TRIAL_CTA_LINE, resolve_affiliate_link, with_trial_cta, write_seo


class TrialCtaHelperTests(unittest.TestCase):
    def test_always_appends_cta_line(self):
        out = with_trial_cta("Hosts walk through Conversation AI setup.", affiliate_url="")
        self.assertIn("Hosts walk through Conversation AI setup.", out)
        self.assertIn(TRIAL_CTA_LINE, out)

    def test_appends_affiliate_link_from_arg(self):
        link = "https://www.gohighlevel.com/william-bootcamp"
        out = with_trial_cta("Episode about Voice AI.", affiliate_url=link)
        self.assertIn(TRIAL_CTA_LINE, out)
        self.assertIn(link, out)

    def test_reads_affiliate_link_env(self):
        env = {"AFFILIATE_LINK": "https://example.com/aff", "GHL_AFFILIATE_LINK": "https://example.com/ignored"}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(resolve_affiliate_link(), "https://example.com/aff")
            out = with_trial_cta("Body")
        self.assertIn("https://example.com/aff", out)

    def test_falls_back_to_ghl_affiliate_link(self):
        env = {"AFFILIATE_LINK": "", "GHL_AFFILIATE_LINK": "https://example.com/ghl-aff"}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(resolve_affiliate_link(), "https://example.com/ghl-aff")
            out = with_trial_cta("Body")
        self.assertIn("https://example.com/ghl-aff", out)

    def test_idempotent_when_cta_and_link_already_present(self):
        link = "https://example.com/aff"
        once = with_trial_cta("Intro", affiliate_url=link)
        twice = with_trial_cta(once, affiliate_url=link)
        self.assertEqual(once.count(TRIAL_CTA_LINE), 1)
        self.assertEqual(twice, once)

    def test_empty_description_still_has_cta(self):
        out = with_trial_cta("", affiliate_url="")
        self.assertEqual(out, TRIAL_CTA_LINE)

    def test_write_seo_without_api_key_includes_cta(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "AFFILIATE_LINK": ""}, clear=False):
            data = write_seo({"title": "T", "body": "Conversation AI body text"})
        self.assertIn(TRIAL_CTA_LINE, data["description"])

    def test_cta_detection_is_case_insensitive(self):
        existing = "Want a GoHighLevel 30-day free trial? LINK IN THE DESCRIPTION."
        out = with_trial_cta(existing, affiliate_url="")
        self.assertEqual(out.count(TRIAL_CTA_LINE), 0)
        self.assertEqual(out.lower().count(TRIAL_CTA_LINE.lower()), 1)

    def test_write_seo_json_success_applies_cta(self):
        import sys

        payload = (
            "```json\n"
            '{"title": "SEO Title", "description": "Listen to this Voice AI walkthrough.", "tags": ["ai"]}\n'
            "```"
        )
        resp = mock.Mock()
        resp.content = [mock.Mock(text=payload)]
        client = mock.Mock()
        client.messages.create.return_value = resp
        anthropic_mod = mock.Mock()
        anthropic_mod.Anthropic.return_value = client
        env = {
            "ANTHROPIC_API_KEY": "sk-test-not-real",
            "AFFILIATE_LINK": "",
            "GHL_AFFILIATE_LINK": "https://example.com/ghl-aff",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch.dict(sys.modules, {"anthropic": anthropic_mod}):
                data = write_seo({"title": "Orig", "body": "Conversation AI body"})
        self.assertEqual(data["title"], "SEO Title")
        self.assertIn(TRIAL_CTA_LINE, data["description"])
        self.assertIn("https://example.com/ghl-aff", data["description"])
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("https://example.com/ghl-aff", prompt)

    def test_write_seo_invalid_json_falls_back_with_cta(self):
        import sys

        resp = mock.Mock()
        resp.content = [mock.Mock(text="not-json")]
        client = mock.Mock()
        client.messages.create.return_value = resp
        anthropic_mod = mock.Mock()
        anthropic_mod.Anthropic.return_value = client
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-not-real", "AFFILIATE_LINK": ""}, clear=False):
            with mock.patch.dict(sys.modules, {"anthropic": anthropic_mod}):
                data = write_seo({"title": "Fallback Title", "body": "x" * 50})
        self.assertEqual(data["title"], "Fallback Title")
        self.assertEqual(data["tags"], [])
        self.assertIn(TRIAL_CTA_LINE, data["description"])

    def test_write_seo_non_object_json_falls_back_with_cta(self):
        import sys

        resp = mock.Mock()
        resp.content = [mock.Mock(text='["title", "description"]')]
        client = mock.Mock()
        client.messages.create.return_value = resp
        anthropic_mod = mock.Mock()
        anthropic_mod.Anthropic.return_value = client
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-not-real", "AFFILIATE_LINK": ""}, clear=False):
            with mock.patch.dict(sys.modules, {"anthropic": anthropic_mod}):
                data = write_seo({"title": "List Title", "body": "Voice AI body"})
        self.assertEqual(data["title"], "List Title")
        self.assertIn(TRIAL_CTA_LINE, data["description"])


if __name__ == "__main__":
    unittest.main()
