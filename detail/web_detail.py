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
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


TIMEOUT_SECONDS = 8
MAX_PAGE_CHARS = 120_000
SEARCH_URL = "https://duckduckgo.com/html/"
BRIGHTDATA_REQUEST_URL = "https://api.brightdata.com/request"


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


def _fetch_text(url: str) -> str:
    return _brightdata_request(url, _brightdata_zone("web")) or _direct_fetch_text(url)


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


def _extract_founders_from_text(text: str, startup_name: str) -> list[str]:
    founders: list[str] = []
    patterns = [
        r"(?:founded by|co-founded by|founders?[:\s]+)([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,2}(?:\s*(?:,|and|&)\s*[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,2})*)",
        r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,2}),?\s+(?:co-)?founder",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidate_group = match.group(1)
            for candidate in re.split(r"\s*(?:,| and | & )\s*", candidate_group):
                candidate = candidate.strip(" .")
                if _looks_like_person_name(candidate, startup_name) and candidate not in founders:
                    founders.append(candidate)
                if len(founders) >= 4:
                    return founders
    return founders


def _looks_like_person_name(candidate: str, startup_name: str) -> bool:
    if not candidate or startup_name.lower() in candidate.lower():
        return False
    words = candidate.split()
    if not 2 <= len(words) <= 3:
        return False
    blocked = {"About Us", "Contact Us", "Privacy Policy", "Terms Service"}
    return candidate not in blocked and all(word[:1].isupper() for word in words)


def _extract_search_titles_from_json(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    titles: list[str] = []

    def walk(value: Any) -> None:
        if len(titles) >= 10:
            return
        if isinstance(value, dict):
            title = value.get("title")
            if isinstance(title, str) and title.strip() and title.strip() not in titles:
                titles.append(title.strip())
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
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


def _hiring_signal(name: str, website_text: str, careers_text: str) -> str:
    combined = f"{website_text} {careers_text}".lower()
    if re.search(r"\b(we'?re hiring|join our team|open roles|job openings|careers|hiring)\b", combined):
        return "hiring"

    search_results = " ".join(_search(f"{name} careers hiring jobs", max_results=2)).lower()
    if re.search(r"\b(careers|jobs|hiring|open roles)\b", search_results):
        return "hiring"
    return "no signal found"


def _funding_summary(name: str) -> str:
    results = _search(f"{name} funding raised", max_results=3)
    if not results:
        return "no funding information found"
    return "Funding signal: " + "; ".join(results[:2])


def _founders(name: str, website_text: str, about_text: str) -> list[str]:
    found = _extract_founders_from_text(f"{about_text} {website_text}", name)
    if found:
        return found

    search_results = _search(f"{name} founder", max_results=3)
    return _extract_founders_from_text(". ".join(search_results), name)


def get_web_detail(name: str, website: str) -> dict[str, Any]:
    """
    Return generic web-derived detail data for any startup source.

    The returned keys are designed to be consumed by detail.synthesis and
    normalized into schema.StartupDetail.
    """
    clean_name = name.strip() or "this startup"
    fallback = _fallback_detail(clean_name)
    base_url = _normalize_url(website)
    if not base_url:
        return fallback

    raw_home = _fetch_text(base_url)
    home_text = _html_to_text(raw_home)
    links = _extract_links(raw_home, base_url) if raw_home else {}

    about_url = links.get("about") or links.get("team") or links.get("founder")
    contact_url = links.get("contact")
    careers_url = links.get("careers") or links.get("jobs")

    about_text = _html_to_text(_fetch_text(about_url)) if about_url else ""
    contact_raw = _fetch_text(contact_url) if contact_url else ""
    contact_text = _html_to_text(contact_raw)
    careers_text = _html_to_text(_fetch_text(careers_url)) if careers_url else ""

    news = _search(f"{clean_name} startup news", max_results=3)

    return {
        "summary": _summarize_site(clean_name, raw_home, home_text),
        "news": news[:3],
        "hiring_signal": _hiring_signal(clean_name, home_text, careers_text),
        "founders": _founders(clean_name, home_text, about_text),
        "funding_summary": _funding_summary(clean_name),
        "contact": _extract_contact(f"{raw_home} {contact_raw}", f"{home_text} {contact_text}", links),
    }
