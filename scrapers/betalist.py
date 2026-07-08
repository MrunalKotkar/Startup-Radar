"""
BetaList scraper for Person 2.

The public entry point is scrape_betalist(), which returns records shaped
exactly like schema.StartupRecord. It accepts an optional fetch_markdown
callable so a Bright Data scrape_as_markdown wrapper can be injected during
the hackathon; without one it uses a small stdlib HTTP fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import re
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from schema import StartupRecord


BASE_URL = "https://betalist.com"
DEFAULT_TIMEOUT_SECONDS = 12
FetchText = Callable[[str], str]


@dataclass(frozen=True)
class _ListingCandidate:
    name: str
    one_liner: str
    slug: str
    detail_url: str


class _BetaListHTMLParser(HTMLParser):
    """Collect visible text and startup links from simple BetaList HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.tokens: list[tuple[str, str, str | None]] = []
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._anchor_href = href
            self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._anchor_href:
            return
        text = _clean_text(" ".join(self._anchor_text))
        if text or "/startups/" in self._anchor_href:
            self.tokens.append(("link", text, self._anchor_href))
        self._anchor_href = None
        self._anchor_text = []

    def handle_data(self, data: str) -> None:
        text = _clean_text(data)
        if not text:
            return
        if self._anchor_href:
            self._anchor_text.append(text)
        else:
            self.tokens.append(("text", text, None))


def scrape_betalist(
    max_pages: int = 3,
    fetch_markdown: FetchText | None = None,
) -> list[StartupRecord]:
    """
    Scrape recent BetaList startups.

    max_pages defaults to 3 per the Person 2 plan. fetch_markdown can be a
    Bright Data scrape_as_markdown wrapper; direct HTTP is used as a fallback.
    """

    if max_pages < 1:
        return []

    fetch = fetch_markdown or _default_fetch_text
    records: list[StartupRecord] = []
    seen: set[str] = set()

    for page_number in range(1, max_pages + 1):
        page_url = _page_url(page_number)
        try:
            listing_text = fetch(page_url)
        except (HTTPError, URLError, TimeoutError, OSError):
            break

        candidates = _parse_listing_page(listing_text, page_url)
        for candidate in candidates:
            key = _normalize_key(candidate.detail_url)
            if key in seen:
                continue
            seen.add(key)

            detail_text = ""
            try:
                detail_text = fetch(candidate.detail_url)
            except (HTTPError, URLError, TimeoutError, OSError):
                pass

            detail = _parse_detail_page(detail_text, candidate.detail_url)
            website = _resolve_external_website(candidate.slug) or candidate.detail_url
            record = _build_record(candidate, detail, website)
            if _is_valid_record(record):
                records.append(record)

    return _dedupe_records(records)


def _page_url(page_number: int) -> str:
    if page_number == 1:
        return BASE_URL + "/"
    return f"{BASE_URL}/?page={page_number}"


def _default_fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "StartupRadar/1.0 (+https://github.com/MrunalKotkar/Startup-Radar)"
        },
    )
    with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _parse_listing_page(text: str, page_url: str = BASE_URL + "/") -> list[_ListingCandidate]:
    tokens = _tokens_from_text(text)
    candidates: list[_ListingCandidate] = []

    for index, token in enumerate(tokens):
        kind, label, href = token
        if kind != "link" or not href:
            continue
        slug = _startup_slug(href)
        if not slug:
            continue

        name = _clean_name(label)
        one_liner = ""
        if not name:
            name, one_liner = _next_name_and_description(tokens, index + 1)
        if not name:
            continue

        if not one_liner:
            one_liner = _next_listing_description(tokens, index + 1)
        if not one_liner:
            one_liner = name

        candidates.append(
            _ListingCandidate(
                name=name,
                one_liner=one_liner,
                slug=slug,
                detail_url=urljoin(page_url, f"/startups/{slug}"),
            )
        )

    return _dedupe_candidates(candidates)


def _parse_detail_page(text: str, detail_url: str) -> dict[str, object]:
    if not text:
        return {"name": "", "one_liner": "", "tags": []}

    tokens = _tokens_from_text(text)
    lines = [_clean_text(token[1]) for token in tokens if _clean_text(token[1])]
    name = _first_markdown_heading(text, "#") or _first_after_marker(lines, "Back to all startups")
    one_liner = _first_markdown_heading(text, "##") or _line_after(lines, name)
    tags = _topics_from_tokens(tokens)

    if not tags:
        tags = _topics_from_markdown(text)

    return {
        "name": _clean_name(name),
        "one_liner": _clean_text(one_liner),
        "tags": tags,
        "website": detail_url,
    }


def _tokens_from_text(text: str) -> list[tuple[str, str, str | None]]:
    if "<html" in text.lower() or "<a " in text.lower():
        parser = _BetaListHTMLParser()
        parser.feed(text)
        return parser.tokens
    return _tokens_from_markdown(text)


def _tokens_from_markdown(text: str) -> list[tuple[str, str, str | None]]:
    tokens: list[tuple[str, str, str | None]] = []
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    for raw_line in text.splitlines():
        line = _clean_text(raw_line.lstrip("#*- "))
        if not line:
            continue

        last_end = 0
        found_link = False
        for match in link_pattern.finditer(raw_line):
            found_link = True
            prefix = _clean_text(raw_line[last_end : match.start()].lstrip("#*- "))
            if prefix:
                tokens.append(("text", prefix, None))
            tokens.append(("link", _clean_text(match.group(1)), match.group(2)))
            last_end = match.end()

        suffix = _clean_text(raw_line[last_end:].lstrip("#*- "))
        if suffix:
            tokens.append(("text", suffix, None))
        elif not found_link:
            tokens.append(("text", line, None))

    return tokens


def _startup_slug(href: str) -> str:
    parsed = urlparse(urljoin(BASE_URL, href))
    match = re.fullmatch(r"/startups/([^/?#]+)", parsed.path)
    if not match:
        return ""
    return match.group(1)


def _next_listing_description(
    tokens: list[tuple[str, str, str | None]],
    start_index: int,
) -> str:
    for kind, label, href in tokens[start_index : start_index + 6]:
        if kind == "link" and href and _startup_slug(href):
            return ""
        text = _clean_text(label)
        if _is_noise_text(text):
            continue
        return text
    return ""


def _next_name_and_description(
    tokens: list[tuple[str, str, str | None]],
    start_index: int,
) -> tuple[str, str]:
    name = ""
    for offset, (kind, label, href) in enumerate(tokens[start_index : start_index + 8]):
        if kind == "link" and href and _startup_slug(href):
            break
        text = _clean_text(label)
        if _is_noise_text(text):
            continue
        if not name:
            name = _clean_name(text)
            continue
        return name, text
    return name, ""


def _topics_from_tokens(tokens: list[tuple[str, str, str | None]]) -> list[str]:
    topics: list[str] = []
    in_topics = False

    for kind, label, _href in tokens:
        text = _clean_text(label)
        if text == "Topics":
            in_topics = True
            continue
        if in_topics and text in {"Featured", "Makers", "Discover startups similar to"}:
            break
        if in_topics and kind == "link" and text and not _is_noise_text(text):
            topics.append(_clean_tag(text))

    return _dedupe_strings([tag for tag in topics if tag])


def _topics_from_markdown(text: str) -> list[str]:
    match = re.search(r"#{1,4}\s*Topics\s*(.+?)(?:\n#{1,4}\s|\Z)", text, re.I | re.S)
    if not match:
        return []
    links = re.findall(r"\[([^\]]+)\]\([^)]+\)", match.group(1))
    return _dedupe_strings([_clean_tag(link) for link in links if _clean_tag(link)])


def _first_markdown_heading(text: str, marker: str) -> str:
    escaped = re.escape(marker)
    for line in text.splitlines():
        stripped = line.strip()
        if re.fullmatch(rf"{escaped}\s+.+", stripped):
            return _clean_text(stripped.removeprefix(marker))
    return ""


def _first_after_marker(lines: list[str], marker: str) -> str:
    for index, line in enumerate(lines):
        if marker in line and index + 1 < len(lines):
            return lines[index + 1]
    return ""


def _line_after(lines: list[str], target: str) -> str:
    if not target:
        return ""
    for index, line in enumerate(lines):
        if line == target and index + 1 < len(lines):
            candidate = lines[index + 1]
            if not _is_noise_text(candidate):
                return candidate
    return ""


def _resolve_external_website(slug: str) -> str:
    visit_url = f"{BASE_URL}/startups/{slug}/visit"
    request = Request(
        visit_url,
        headers={
            "User-Agent": "StartupRadar/1.0 (+https://github.com/MrunalKotkar/Startup-Radar)"
        },
    )
    try:
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
    except (HTTPError, URLError, TimeoutError, OSError):
        return ""

    final_host = urlparse(final_url).netloc.lower()
    if final_host.endswith("betalist.com"):
        return ""
    return final_url


def _build_record(
    candidate: _ListingCandidate,
    detail: dict[str, object],
    website: str,
) -> StartupRecord:
    name = _clean_name(str(detail.get("name") or candidate.name))
    one_liner = _clean_text(str(detail.get("one_liner") or candidate.one_liner))
    tags = detail.get("tags")
    clean_tags = _dedupe_strings(
        [_clean_tag(tag) for tag in tags if isinstance(tag, str)]
        if isinstance(tags, list)
        else []
    )

    return {
        "name": name,
        "one_liner": one_liner,
        "tags": clean_tags,
        "website": website,
        "source": "BetaList",
    }


def _is_valid_record(record: StartupRecord) -> bool:
    return bool(record["name"] and record["one_liner"] and record["website"])


def _dedupe_candidates(candidates: list[_ListingCandidate]) -> list[_ListingCandidate]:
    deduped: list[_ListingCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.slug or _normalize_key(candidate.name)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _dedupe_records(records: list[StartupRecord]) -> list[StartupRecord]:
    deduped: list[StartupRecord] = []
    seen: set[str] = set()
    for record in records:
        key = _normalize_key(record["website"]) or _normalize_key(record["name"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _normalize_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _clean_name(value: str) -> str:
    name = _clean_text(value)
    name = re.sub(r"\s+BOOSTED\b", "", name, flags=re.I).strip()
    return name


def _clean_tag(value: str) -> str:
    return _clean_text(value).strip(" ,")


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _is_noise_text(text: str) -> bool:
    if not text:
        return True
    lowered = text.lower()
    if lowered in {
        "image",
        "boosted",
        "visit site",
        "today",
        "yesterday",
        "load next page...",
        "load next page…",
        "submit startup",
        "sign in",
        "log in",
    }:
        return True
    if re.fullmatch(r"(today|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday).+", lowered):
        return True
    if re.fullmatch(r"[a-z]+day\s+[a-z]+\s+\d+(st|nd|rd|th)?", lowered):
        return True
    return False


if __name__ == "__main__":
    for startup in scrape_betalist():
        print(startup)
