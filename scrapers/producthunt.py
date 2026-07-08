"""
scrape_producthunt() -- Person 1

Pulls startups from the Product Hunt homepage via Bright Data and returns
them in the shared StartupRecord shape (schema.py).

Verified live before writing this parser:
  - https://www.producthunt.com/ renders real product data server-side
    (unlike YC's root directory) -- no infinite-scroll problem here.
  - The homepage has four sections ("Top Products Launching Today",
    "Yesterday's Top Products", "Last Week's Top Products", "Last Month's
    Top Products"), each a numbered list (rank resets to 1 per section, so
    dedupe by slug, not rank). ~19 + 5 + 5 + 5 = ~34 unique products total.
  - Each product is one predictable markdown line:
        [{rank}\\. {name}](/products/{slug}){one_liner}
    followed shortly after by a tags line:
        [{tag1}](/topics/{slug1})•[{tag2}](/topics/{slug2})•...
  - The listing does NOT include the company's real external website --
    only the Product Hunt product page. The real site is on that product's
    detail page as "[Visit website](https://example.com/?ref=producthunt)"
    -- the "?ref=producthunt" query param is stripped before storing it.
    Resolving it costs one extra Bright Data call per product.
"""

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema import StartupRecord
from scrapers._brightdata import BrightDataError, fetch_markdown

PH_HOMEPAGE = "https://www.producthunt.com/"
PH_BASE = "https://www.producthunt.com"

_PRODUCT_LINE = re.compile(r"\[(\d+)\\\.\s*([^\]]+)\]\(/products/([a-z0-9-]+)\)([^\n]*)")
_TAGS_BLOCK = re.compile(r"((?:\[[^\]]+\]\(/topics/[^)]+\)•?)+)")
_TAG = re.compile(r"\[([^\]]+)\]\(/topics/[^)]+\)")
_VISIT_WEBSITE = re.compile(r"\[Visit website\]\(([^)]+)\)")


def _parse_homepage(markdown: str) -> list[dict]:
    """Extract per-product dicts (name, slug, one_liner, tags) from the PH homepage markdown."""
    products = []
    for match in _PRODUCT_LINE.finditer(markdown):
        _rank, name, slug, one_liner = match.groups()
        one_liner = one_liner.strip()

        tail = markdown[match.end():match.end() + 400]
        tags_match = _TAGS_BLOCK.search(tail)
        tags = _TAG.findall(tags_match.group(1)) if tags_match else []

        products.append({"name": name.strip(), "slug": slug, "one_liner": one_liner, "tags": tags})
    return products


def _resolve_website(slug: str) -> str | None:
    """Fetch a Product Hunt product page and pull the real external "Visit website" link."""
    try:
        markdown = fetch_markdown(f"{PH_BASE}/products/{slug}")
    except BrightDataError:
        return None

    match = _VISIT_WEBSITE.search(markdown)
    if not match:
        return None

    url = match.group(1)
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def scrape_producthunt(limit: int = 25, resolve_website: bool = True) -> list[StartupRecord]:
    """
    Scrape today's/recent Product Hunt launches from the homepage.

    limit: max products to process (across all four homepage sections,
        deduped by slug). Each one costs an extra Bright Data call to
        resolve its real website, so this keeps bulk-scrape cost/time sane.
    resolve_website: if False, skips the extra per-product call and falls
        back to the Product Hunt product page URL as "website" (degrades
        gracefully rather than crashing).
    """
    try:
        markdown = fetch_markdown(PH_HOMEPAGE)
    except BrightDataError as e:
        print(f"[scrape_producthunt] failed to fetch homepage: {e}")
        return []

    seen_slugs: set[str] = set()
    records: list[StartupRecord] = []

    for product in _parse_homepage(markdown):
        slug = product["slug"]
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        if len(records) >= limit:
            break

        website = None
        if resolve_website:
            website = _resolve_website(slug)
        if not website:
            website = f"{PH_BASE}/products/{slug}"

        records.append(
            StartupRecord(
                name=product["name"],
                one_liner=product["one_liner"],
                tags=product["tags"],
                website=website,
                source="ProductHunt",
            )
        )

    return records


if __name__ == "__main__":
    import json

    results = scrape_producthunt()
    print(f"Scraped {len(results)} Product Hunt startups")
    print(json.dumps(results[:3], indent=2))
