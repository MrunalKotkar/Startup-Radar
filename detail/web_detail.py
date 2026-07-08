"""
Generic web-detail extraction for any startup source.

When Bright Data credentials are configured, this module uses Bright Data's
HTTP API first for page fetches and SERP-style searches. If credentials,
zones, or network calls are unavailable, every call falls back gracefully and
still returns schema-compatible values.
"""

from __future__ import annotations

import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()

TIMEOUT_SECONDS = 8
MAX_PAGE_CHARS = 120_000
SEARCH_URL = "https://duckduckgo.com/html/"
BRIGHTDATA_REQUEST_URL = "https://api.brightdata.com/request"

# Shared across calls rather than created per-request: _fetch_text races a
# direct fetch against Bright Data and often doesn't wait for the losing
# side, so a fresh ThreadPoolExecutor's context-manager exit (which blocks
# until every submitted future finishes) would defeat the point.
_POOL = ThreadPoolExecutor(max_workers=16)


def _fallback_detail(name: str) -> dict[str, Any]:
    return {
        "summary": f"No live website summary found for {name}.",
        "news": [],
        "hiring_signal": "no signal found",
        "founders": [],
        "funding_summary": "no funding information found",
        "contact": None,
    }


def _normalize_url(website: str) -> str | None:
    cleaned = website.strip()
    if not cleaned:
        return None
    if not re.match(r"^https?://", cleaned, flags=re.IGNORECASE):
        cleaned = f"https://{cleaned}"

    parsed = urlparse(cleaned)
    if not parsed.netloc:
        return None
    return cleaned


def _brightdata_api_key() -> str | None:
    return os.getenv("BRIGHTDATA_API_KEY") or os.getenv("BRIGHTDATA_API_TOKEN") or os.getenv("BRIGHT_DATA_API_KEY")


def _brightdata_zone(kind: str) -> str | None:
    if kind == "serp":
        return (
            os.getenv("BRIGHTDATA_SERP_ZONE")
            or os.getenv("BRIGHTDATA_SEARCH_ZONE")
            or os.getenv("BRIGHTDATA_ZONE")
        )
    return (
        os.getenv("BRIGHTDATA_WEB_UNLOCKER_ZONE")
        or os.getenv("BRIGHTDATA_WEB_ZONE")
        or os.getenv("BRIGHTDATA_ZONE")
    )


def _decode_response(raw: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding, errors="ignore")
        except LookupError:
            continue
    return ""


def _brightdata_request(url: str, zone: str | None) -> str:
    api_key = _brightdata_api_key()
    if not api_key or not zone:
        return ""

    payload = json.dumps({"zone": zone, "url": url, "format": "raw"}).encode("utf-8")
    request = Request(
        BRIGHTDATA_REQUEST_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Startup-Radar/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return _decode_response(response.read(MAX_PAGE_CHARS))
    except (HTTPError, URLError, TimeoutError, OSError):
        return ""


def _direct_fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Startup-Radar/1.0",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("content-type", "")
            if "text" not in content_type and "html" not in content_type and content_type:
                return ""
            raw = response.read(MAX_PAGE_CHARS)
    except (HTTPError, URLError, TimeoutError, OSError):
        return ""

    return _decode_response(raw)


def _looks_like_real_page(raw: str) -> bool:
    return len(raw) > 2000 and bool(re.search(r"<(html|body)[\s>]", raw, re.IGNORECASE))


def _fetch_text(url: str) -> str:
    """Race a direct fetch against Bright Data instead of trying one then
    the other. Most sites don't need unlocking at all (confirmed live:
    razorpay.com times out Bright Data's full 8s and returns nothing, while
    a plain fetch succeeds in ~1s) -- always waiting out that timeout first
    dominated total detail-synthesis time. Direct fetch wins immediately if
    it looks like a real page; otherwise fall back to whichever Bright Data
    call was already running in the background (needed for JS-rendered/
    bot-protected sites where direct fetch returns an empty app shell)."""
    direct_future = _POOL.submit(_direct_fetch_text, url)
    bd_future = _POOL.submit(_brightdata_request, url, _brightdata_zone("web"))

    direct_result = direct_future.result()
    if _looks_like_real_page(direct_result):
        return direct_result

    return bd_future.result() or direct_result


def _html_to_text(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"(?is)<(script|style|noscript|svg).*?>.*?</\1>", " ", raw)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|li|h[1-6]|section|article)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_meta_description(raw: str) -> str | None:
    patterns = [
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            value = html.unescape(match.group(1)).strip()
            if value:
                return re.sub(r"\s+", " ", value)
    return None


def _first_sentences(text: str, limit: int = 2) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    useful = [sentence.strip() for sentence in sentences if len(sentence.strip()) > 30]
    summary = " ".join(useful[:limit]).strip()
    if summary:
        return summary[:500].rstrip()
    return text[:280].strip()


def _summarize_site(name: str, raw: str, text: str) -> str:
    meta = _extract_meta_description(raw)
    if meta:
        return meta[:500].rstrip()
    if text:
        return _first_sentences(text)
    return f"No live website summary found for {name}."


def _extract_links(raw: str, base_url: str) -> dict[str, str]:
    links: dict[str, str] = {}
    for href, label in re.findall(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', raw):
        clean_label = _html_to_text(label).lower()
        clean_href = href.strip()
        if not clean_href or clean_href.startswith(("#", "javascript:", "mailto:")):
            continue
        absolute = urljoin(base_url, clean_href)
        combined = f"{clean_label} {absolute}".lower()
        for key in ("about", "team", "founder", "contact", "careers", "jobs"):
            if key in combined and key not in links:
                links[key] = absolute
    return links


def _extract_contact(raw: str, text: str, links: dict[str, str]) -> str | None:
    email_match = re.search(
        r"\b(?:hello|info|contact|support|team|founders?)@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",
        text,
        flags=re.IGNORECASE,
    )
    if email_match:
        return email_match.group(0)

    mailto_match = re.search(r'href=["\']mailto:([^"\'>?]+)', raw, flags=re.IGNORECASE)
    if mailto_match:
        return mailto_match.group(1)

    return links.get("contact")


_NAME = r"[A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+){1,2}"
_NAME_LIST = rf"{_NAME}(?:\s*(?:,|and|&)\s*{_NAME})*"

# Real bios come in a few shapes: "founded by X and Y", "X, co-founder of...",
# and -- very common in company blurbs -- "X (CEO & Co-Founder)". The keyword
# itself needs case-insensitive matching (source text is often "Co-Founder",
# not "co-founder"), scoped with (?i:...) so it doesn't loosen the name
# pattern itself (names must still start with a capital letter).
_FOUNDER_PATTERNS = [
    rf"(?i:founded by|co-founded by)\s+({_NAME_LIST})",
    rf"(?i:founders?)[:\s]+({_NAME_LIST})",
    rf"({_NAME}),?\s+(?:is\s+)?(?:the\s+)?(?i:co-founder|founder)\b",
    rf"({_NAME})\s*\([^)]*(?i:co-founder|founder)[^)]*\)",
]


def _extract_founders_from_text(text: str, startup_name: str) -> list[str]:
    founders: list[str] = []
    for pattern in _FOUNDER_PATTERNS:
        for match in re.finditer(pattern, text):
            candidate_group = match.group(1)
            for candidate in re.split(r"\s*(?:,| and | & )\s*", candidate_group):
                candidate = candidate.strip(" .")
                if _looks_like_person_name(candidate, startup_name) and candidate not in founders:
                    founders.append(candidate)
                if len(founders) >= 4:
                    return founders
    return founders


_STOPWORDS = {
    "the", "he", "she", "they", "it", "this", "that", "also", "and", "or",
    "but", "his", "her", "their", "our", "your", "its", "who", "which",
    "about", "contact", "privacy", "terms", "founder", "founders", "ceo",
    "cto", "coo", "team", "read", "more", "learn",
}


def _looks_like_person_name(candidate: str, startup_name: str) -> bool:
    if not candidate or startup_name.lower() in candidate.lower():
        return False
    words = candidate.split()
    if not 2 <= len(words) <= 3:
        return False
    if any(word.lower() in _STOPWORDS for word in words):
        return False
    blocked = {"About Us", "Contact Us", "Privacy Policy", "Terms Service"}
    return candidate not in blocked and all(word[:1].isupper() for word in words)


def _extract_search_titles_from_json(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, dict):
        return []

    # Bright Data's brd_json=1 SERP response puts real organic results under
    # "organic" -- other top-level keys like "navigation" (Google's own tab
    # labels: "News", "Images", "AI Mode"...) also have "title" fields and
    # must NOT be treated as search results.
    organic = data.get("organic")
    if not isinstance(organic, list):
        return []

    titles: list[str] = []
    for item in organic:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        if isinstance(title, str) and title.strip() and title.strip() not in titles:
            titles.append(title.strip())
        if len(titles) >= 10:
            break
    return titles


def _extract_search_titles_from_html(raw: str, max_results: int) -> list[str]:
    results: list[str] = []
    patterns = [
        r'(?is)<a[^>]+class=["\']result__a["\'][^>]*>(.*?)</a>',
        r'(?is)<h3[^>]*>(.*?)</h3>',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, raw):
            title = _html_to_text(match.group(1))
            if title and title not in results:
                results.append(title)
            if len(results) >= max_results:
                return results
    return results


def _brightdata_search(query: str, max_results: int) -> list[str]:
    serp_zone = _brightdata_zone("serp")
    if not serp_zone:
        return []

    google_url = f"https://www.google.com/search?{urlencode({'q': query, 'brd_json': '1'})}"
    raw = _brightdata_request(google_url, serp_zone)
    if not raw:
        return []

    return (_extract_search_titles_from_json(raw) or _extract_search_titles_from_html(raw, max_results))[:max_results]


def _direct_search(query: str, max_results: int) -> list[str]:
    request_url = f"{SEARCH_URL}?q={query.replace(' ', '+')}"
    raw = _direct_fetch_text(request_url)
    if not raw:
        return []

    return _extract_search_titles_from_html(raw, max_results)


def _search(query: str, max_results: int = 3) -> list[str]:
    return _brightdata_search(query, max_results) or _direct_search(query, max_results)


def _extract_search_descriptions_from_json(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, dict):
        return []

    organic = data.get("organic")
    if not isinstance(organic, list):
        return []

    descriptions: list[str] = []
    for item in organic:
        if not isinstance(item, dict):
            continue
        description = item.get("description")
        if isinstance(description, str) and description.strip() and description.strip() not in descriptions:
            descriptions.append(description.strip())
        if len(descriptions) >= 10:
            break
    return descriptions


def _search_snippets(query: str, max_results: int = 5) -> list[str]:
    """Search result descriptions, not titles -- titles rarely contain a
    founder's name, but the prose snippet underneath often does. Only
    available via Bright Data's SERP JSON; degrades to [] otherwise, which
    just means founder lookup falls back to whatever the page text found."""
    serp_zone = _brightdata_zone("serp")
    if not serp_zone:
        return []

    google_url = f"https://www.google.com/search?{urlencode({'q': query, 'brd_json': '1'})}"
    raw = _brightdata_request(google_url, serp_zone)
    if not raw:
        return []

    return _extract_search_descriptions_from_json(raw)[:max_results]


def _resolve_hiring_signal(website_text: str, careers_text: str, search_results: list[str]) -> str:
    combined = f"{website_text} {careers_text}".lower()
    if re.search(r"\b(we'?re hiring|join our team|open roles|job openings|careers|hiring)\b", combined):
        return "hiring"

    search_text = " ".join(search_results).lower()
    if re.search(r"\b(careers|jobs|hiring|open roles)\b", search_text):
        return "hiring"
    return "no signal found"


def _resolve_funding_summary(search_results: list[str]) -> str:
    if not search_results:
        return "no funding information found"
    return "Funding signal: " + "; ".join(search_results[:2])


def _resolve_founders(name: str, website_text: str, about_text: str, search_snippets: list[str]) -> list[str]:
    found = _extract_founders_from_text(f"{about_text} {website_text}", name)
    if found:
        return found

    return _extract_founders_from_text(". ".join(search_snippets), name)


def get_web_detail(name: str, website: str) -> dict[str, Any]:
    """
    Return generic web-derived detail data for any startup source.

    The returned keys are designed to be consumed by detail.synthesis and
    normalized into schema.StartupDetail.

    Performance note: this used to run every page fetch and every search
    query one after another (up to 8 sequential network calls, each able to
    burn a full 8s Bright Data timeout before falling back -- worst case
    well over a minute). Two fixes: (1) _fetch_text races Bright Data
    against a direct fetch instead of trying one then the other, since most
    sites don't need unlocking at all; (2) the four name-only searches don't
    depend on the homepage, so they're fired off at the same time as the
    homepage fetch instead of after it -- only the about/contact/careers
    fetches have to wait, since they need links discovered from the homepage.
    """
    clean_name = name.strip() or "this startup"
    fallback = _fallback_detail(clean_name)
    base_url = _normalize_url(website)
    if not base_url:
        return fallback

    home_future = _POOL.submit(_fetch_text, base_url)
    news_future = _POOL.submit(_search, f"{clean_name} startup news", 3)
    hiring_future = _POOL.submit(_search, f"{clean_name} careers hiring jobs", 2)
    funding_future = _POOL.submit(_search, f"{clean_name} funding raised", 3)
    founders_future = _POOL.submit(_search_snippets, f"{clean_name} founder", 5)

    raw_home = home_future.result()
    home_text = _html_to_text(raw_home)
    links = _extract_links(raw_home, base_url) if raw_home else {}

    about_url = links.get("about") or links.get("team") or links.get("founder")
    contact_url = links.get("contact")
    careers_url = links.get("careers") or links.get("jobs")

    about_future = _POOL.submit(_fetch_text, about_url) if about_url else None
    contact_future = _POOL.submit(_fetch_text, contact_url) if contact_url else None
    careers_future = _POOL.submit(_fetch_text, careers_url) if careers_url else None

    contact_raw = contact_future.result() if contact_future else ""
    about_text = _html_to_text(about_future.result()) if about_future else ""
    careers_text = _html_to_text(careers_future.result()) if careers_future else ""
    news = news_future.result()
    hiring_search_results = hiring_future.result()
    funding_search_results = funding_future.result()
    founder_snippets = founders_future.result()

    contact_text = _html_to_text(contact_raw)

    return {
        "summary": _summarize_site(clean_name, raw_home, home_text),
        "news": news[:3],
        "hiring_signal": _resolve_hiring_signal(home_text, careers_text, hiring_search_results),
        "founders": _resolve_founders(clean_name, home_text, about_text, founder_snippets),
        "funding_summary": _resolve_funding_summary(funding_search_results),
        "contact": _extract_contact(f"{raw_home} {contact_raw}", f"{home_text} {contact_text}", links),
    }
