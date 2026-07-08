"""
scrape_yc() -- Person 1

Pulls startups from the YC directory via Bright Data and returns them in the
shared StartupRecord shape (schema.py).

Verified live before writing this parser (see conversation / commit notes):
  - https://www.ycombinator.com/companies (no filter) is almost entirely
    client-rendered -- Bright Data's single-shot fetch returns just the page
    title, no company data. Not usable.
  - https://www.ycombinator.com/companies/industry/{slug} pages DO render a
    real, parseable list of companies server-side -- but only the first ~50
    (the page relies on infinite scroll for more; the markdown output ends
    with the literal text "Loading more companies..."). Getting beyond 50
    per industry would need browser-automation (scroll simulation), which
    the project plan explicitly flags as the expensive path to avoid.
  - Each company card in that markdown is a predictable block of blank-line
    separated paragraphs:
        [](/companies/{slug})*   [](/companies/{slug})   <- delimiter
        [](/companies/{slug})[![name](logo)](/companies/{slug})
        [{name}
        Y Combinator Logo{batch}
         • Active • N employees • City](/companies/{slug})  <- closes the link
        {one_liner}
        {tag}
        {tag}
        ...
  - The bulk listing does NOT include the company's real external website --
    only Bright Data's internal /companies/{slug} link. The real site is on
    the individual company page as a self-referential markdown link, e.g.
    "[https://screenpipe.com](https://screenpipe.com)". Resolving it costs
    one extra Bright Data call per company.
"""

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema import StartupRecord
from scrapers._brightdata import BrightDataError, fetch_markdown

YC_BASE = "https://www.ycombinator.com"

# Confirmed valid live against the real YC site before being hardcoded here.
DEFAULT_INDUSTRIES = [
    "artificial-intelligence",
    "developer-tools",
    "fintech",
    "healthcare",
    "b2b",
    "consumer",
]

# Domains that show up as external-looking links on a YC company page but
# are never the company's own site -- skip these when resolving "website".
_NON_COMPANY_DOMAINS = (
    "ycombinator.com",
    "bookface-images.s3.amazonaws.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "crunchbase.com",
    "startupschool.org",
    "news.ycombinator.com",
    "github.com/ycombinator",
)


def _shorten_one_liner(text: str, max_chars: int = 140) -> str:
    """Cap YC's description to an actual one-liner.

    YC's directory shows a short tagline for most companies but a full
    multi-paragraph bio for others (observed: Razorpay, GitLab, etc. --
    several hundred to 2000+ characters) with no length cap in the source
    markup itself, so this has to be enforced on our side.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return text

    first_sentence = re.split(r"(?<=[.!?])\s+", text)[0].strip()
    if len(first_sentence) <= max_chars:
        return first_sentence

    truncated = text[:max_chars].rsplit(" ", 1)[0].rstrip(",;:. ")
    return truncated + "…"


def _parse_industry_page(markdown: str) -> list[dict]:
    """Split one industry page's markdown into per-company dicts (name, slug, one_liner, tags)."""
    chunks = re.split(r"(?=^\[\]\(/companies/[a-z0-9-]+\)\*)", markdown, flags=re.MULTILINE)
    companies = []
    for chunk in chunks:
        slug_match = re.search(r"/companies/([a-z0-9-]+)\)\*", chunk)
        if not slug_match:
            continue
        slug = slug_match.group(1)

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", chunk.strip())]

        name = None
        link_end_idx = None
        for i, p in enumerate(paragraphs):
            if p.startswith("[") and not p.startswith("[](") and "![" not in p and "Y Combinator Logo" not in p:
                name = p.lstrip("[").strip()
                for j in range(i, len(paragraphs)):
                    if f"](/companies/{slug})" in paragraphs[j]:
                        link_end_idx = j
                        break
                break

        if name is None or link_end_idx is None:
            continue

        one_liner = paragraphs[link_end_idx + 1].strip() if link_end_idx + 1 < len(paragraphs) else ""
        if not one_liner or "](" in one_liner:
            continue

        tags = []
        for p in paragraphs[link_end_idx + 2:]:
            if not p or "](" in p or len(p) > 60 or p.endswith("."):
                break
            tags.append(p)

        companies.append({"name": name, "slug": slug, "one_liner": _shorten_one_liner(one_liner), "tags": tags})
    return companies


def _resolve_website(slug: str) -> str | None:
    """Fetch a YC company's detail page and pull its real external website, if listed."""
    try:
        markdown = fetch_markdown(urljoin(YC_BASE, f"/companies/{slug}"))
    except BrightDataError:
        return None

    for match in re.finditer(r"\[(https?://[^\]\s]+)\]\(\1\)", markdown):
        url = match.group(1)
        if not any(domain in url for domain in _NON_COMPANY_DOMAINS):
            return url
    return None


def scrape_yc(
    filters: list[str] | None = None,
    limit: int = 20,
    per_industry_limit: int = 15,
    resolve_website: bool = True,
) -> list[StartupRecord]:
    """
    Scrape YC startups across a set of industry pages.

    filters: YC industry slugs, e.g. ["fintech", "healthcare"]. Defaults to
        DEFAULT_INDUSTRIES (all confirmed valid live).
    limit: total companies to return across all industries combined. Stops
        as soon as this is reached, so cost/time stay predictable regardless
        of how many industries are configured.
    per_industry_limit: cap per industry page -- each page yields up to 50
        companies, but resolving the real website costs one extra Bright
        Data call per company, so this keeps bulk-scrape time/cost sane.
    resolve_website: if False, skips the extra per-company call and falls
        back to the YC company page URL as "website" (degrades gracefully
        rather than crashing -- that page still has a mission/description
        Person 3's detail scrape can use, just not the real external site).
    """
    industries = filters if filters is not None else DEFAULT_INDUSTRIES
    seen_slugs: set[str] = set()
    records: list[StartupRecord] = []

    for industry in industries:
        if len(records) >= limit:
            break

        try:
            markdown = fetch_markdown(urljoin(YC_BASE, f"/companies/industry/{industry}"))
        except BrightDataError as e:
            print(f"[scrape_yc] skipping industry '{industry}': {e}")
            continue

        companies = _parse_industry_page(markdown)[:per_industry_limit]
        for company in companies:
            if len(records) >= limit:
                break

            slug = company["slug"]
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            website = None
            if resolve_website:
                website = _resolve_website(slug)
            if not website:
                website = urljoin(YC_BASE, f"/companies/{slug}")

            records.append(
                StartupRecord(
                    name=company["name"],
                    one_liner=company["one_liner"],
                    tags=company["tags"],
                    website=website,
                    source="YC",
                )
            )

    return records


if __name__ == "__main__":
    import json

    results = scrape_yc()
    print(f"Scraped {len(results)} YC startups")
    print(json.dumps(results[:3], indent=2))
