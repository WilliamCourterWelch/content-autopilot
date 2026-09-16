import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.publishers import publish_ghl_site


class SiteUpgradeTests(unittest.TestCase):
    def test_no_pillar_refuses_thin_new_page(self):
        with mock.patch("scripts.dedupe.load_pillar_pages", return_value=[]):
            result = publish_ghl_site(
                {
                    "title": "Conversation AI bot",
                    "source_url": "https://help.gohighlevel.com/support/solutions/articles/155000004401-x",
                    "publish_url": "https://globalhighlevel.com/new-thin-post",
                }
            )
        self.assertEqual(result["channel"], "ghl-site")
        self.assertIn(result["status"], ("skipped", "blocked"))
        self.assertIn("thin new HTML", result["reason"])

    def test_pillar_match_writes_fold_brief_not_new_url(self):
        pillar = {
            "url": "https://globalhighlevel.com/conversation-ai",
            "title": "Conversation AI",
            "keywords": ["conversation ai"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            upgrade = Path(tmp) / "site-upgrades"
            with mock.patch("scripts.dedupe.load_pillar_pages", return_value=[pillar]):
                with mock.patch("scripts.publishers.UPGRADE_DIR", upgrade):
                    result = publish_ghl_site(
                        {
                            "title": "How to set up a Conversation AI bot",
                            "source_url": "https://help.gohighlevel.com/x",
                        }
                    )
            self.assertEqual(result["status"], "queued-upgrade")
            self.assertEqual(result["url"], pillar["url"])
            briefs = list(upgrade.glob("*.json"))
            self.assertEqual(len(briefs), 1)
            body = json.loads(briefs[0].read_text(encoding="utf-8"))
            self.assertEqual(body["action"], "fold-into-existing-page")
            self.assertNotIn("new-thin-post", body["pillar_url"])

    def test_newsletter_is_not_a_publish_target(self):
        from scripts.distribution import CHANNELS, FORMAT_CHANNEL_MATRIX

        self.assertNotIn("newsletter", CHANNELS)
        for chans in FORMAT_CHANNEL_MATRIX.values():
            self.assertNotIn("newsletter", chans)


if __name__ == "__main__":
    unittest.main()
