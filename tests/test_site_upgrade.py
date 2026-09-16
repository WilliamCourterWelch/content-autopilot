import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.publishers import publish_ghl_site, publish_newsletter


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

    def test_newsletter_skips_without_inventing_a_list(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            result = publish_newsletter({"title": "x"})
        self.assertEqual(result["status"], "skipped")
        self.assertIn("do not invent", result["reason"].lower())


if __name__ == "__main__":
    unittest.main()
