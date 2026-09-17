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


if __name__ == "__main__":
    unittest.main()
