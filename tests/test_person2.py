import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scrapers.betalist import _parse_detail_page, _parse_listing_page, scrape_betalist
from scrapers.merge import load_startups, merge_sources, write_startups


LISTING_HTML = """
<html><body>
  <a href="/startups/alpha-ai">Alpha AI</a>
  <p>Automate customer support with AI agents</p>
  <a href="/startups/beta-dev">Beta Dev</a>
  <p>Developer tools for fast API testing</p>
  <a href="/startups/gamma-finance">Gamma Finance</a>
  <p>Track invoices and cash flow in one dashboard</p>
  <a class="absolute inset-0" href="/startups/delta-rows"></a>
  <span>Delta Rows</span>
  <span>Turn spreadsheets into lightweight internal tools</span>
  <a href="/startups/alpha-ai">Alpha AI</a>
  <p>Duplicate listing should be ignored</p>
</body></html>
"""


DETAIL_MARKDOWN = """
# Alpha AI
## Better AI support for small teams

Longer description that the current schema does not need.

### Topics
[AI Tools](https://betalist.com/topics/ai-tools)
[Customer Support](https://betalist.com/topics/customer-support)
[SaaS](https://betalist.com/topics/saas)

### Featured
July 8, 2026
"""


class BetaListScraperTests(unittest.TestCase):
    def test_listing_parser_extracts_startup_candidates(self):
        candidates = _parse_listing_page(LISTING_HTML)

        self.assertEqual(len(candidates), 4)
        self.assertEqual(candidates[0].name, "Alpha AI")
        self.assertEqual(candidates[0].one_liner, "Automate customer support with AI agents")
        self.assertEqual(candidates[0].slug, "alpha-ai")
        self.assertEqual(candidates[3].name, "Delta Rows")
        self.assertEqual(candidates[3].one_liner, "Turn spreadsheets into lightweight internal tools")

    def test_detail_parser_extracts_topics(self):
        detail = _parse_detail_page(DETAIL_MARKDOWN, "https://betalist.com/startups/alpha-ai")

        self.assertEqual(detail["name"], "Alpha AI")
        self.assertEqual(detail["one_liner"], "Better AI support for small teams")
        self.assertEqual(detail["tags"], ["AI Tools", "Customer Support", "SaaS"])

    def test_scrape_betalist_uses_required_shape_and_fallback_website(self):
        pages = {
            "https://betalist.com/": LISTING_HTML,
            "https://betalist.com/startups/alpha-ai": DETAIL_MARKDOWN,
            "https://betalist.com/startups/beta-dev": """
                # Beta Dev
                ## Developer tools for fast API testing
                ### Topics
                [Developer Tools](https://betalist.com/topics/developer-tools)
            """,
            "https://betalist.com/startups/gamma-finance": """
                # Gamma Finance
                ## Track invoices and cash flow in one dashboard
                ### Topics
                [Finance](https://betalist.com/topics/finance)
            """,
            "https://betalist.com/startups/delta-rows": """
                # Delta Rows
                ## Turn spreadsheets into lightweight internal tools
                ### Topics
                [Productivity](https://betalist.com/topics/productivity)
            """,
        }

        with patch("scrapers.betalist._resolve_external_website", return_value=""):
            records = scrape_betalist(max_pages=1, fetch_markdown=pages.__getitem__)

        self.assertEqual(len(records), 4)
        for record in records:
            self.assertEqual(set(record), {"name", "one_liner", "tags", "website", "source"})
            self.assertEqual(record["source"], "BetaList")
            self.assertTrue(record["website"].startswith("https://betalist.com/startups/"))


class MergeTests(unittest.TestCase):
    def test_merge_dedupes_by_website_and_first_source_wins(self):
        yc = [
            {
                "name": "Alpha AI",
                "one_liner": "YC version wins",
                "tags": ["AI"],
                "website": "https://www.alpha.ai/?ref=yc",
                "source": "YC",
            }
        ]
        betalist = [
            {
                "name": "Alpha AI",
                "one_liner": "BetaList duplicate",
                "tags": ["AI Tools"],
                "website": "http://alpha.ai",
                "source": "BetaList",
            }
        ]

        merged = merge_sources(yc, betalist)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["one_liner"], "YC version wins")

    def test_merge_dedupes_by_name_when_website_missing(self):
        product_hunt = [
            {
                "name": "Beta Dev",
                "one_liner": "First",
                "tags": [],
                "website": "",
                "source": "ProductHunt",
            }
        ]
        betalist = [
            {
                "name": "  beta   dev ",
                "one_liner": "Second",
                "tags": [],
                "website": "",
                "source": "BetaList",
            }
        ]

        merged = merge_sources(product_hunt, betalist)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source"], "ProductHunt")

    def test_write_and_load_startups_json(self):
        records = merge_sources(
            [
                {
                    "name": "Gamma Finance",
                    "one_liner": "Track invoices",
                    "tags": ["Finance"],
                    "website": "https://gamma.example",
                    "source": "BetaList",
                }
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "startups.json"
            write_startups(records, str(path))
            loaded = load_startups(str(path))

        self.assertEqual(loaded, records)
        self.assertIsInstance(json.dumps(loaded), str)


if __name__ == "__main__":
    unittest.main()
