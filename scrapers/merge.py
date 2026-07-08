"""
Merge and dedupe StartupRecord lists from all bulk sources.

Person 2 owns this module. It intentionally depends only on stdlib code and
the frozen schema contract so Person 1 can plug in YC/Product Hunt output
without changing merge behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Iterable
from urllib.parse import urlparse

from schema import StartupRecord


DEFAULT_OUTPUT_PATH = "data/startups.json"


def merge_sources(*sources: list[StartupRecord]) -> list[StartupRecord]:
    """
    Merge source outputs with deterministic first-source-wins dedupe.

    Dedupe by normalized website first, then normalized name. Final output is
    sorted by normalized name so generated JSON has stable diffs.
    """

    deduped: list[StartupRecord] = []
    seen: set[str] = set()

    for record in _flatten(sources):
        clean_record = _clean_record(record)
        key = _dedupe_key(clean_record)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(clean_record)

    return sorted(deduped, key=lambda item: _normalize_name(item["name"]))


def write_startups(
    records: list[StartupRecord],
    output_path: str = DEFAULT_OUTPUT_PATH,
) -> None:
    """Write generated startup data as a pretty JSON array."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output_file:
        json.dump(records, output_file, indent=2, ensure_ascii=False)
        output_file.write("\n")


def load_startups(path: str = DEFAULT_OUTPUT_PATH) -> list[StartupRecord]:
    """Load startup records from generated JSON."""

    with Path(path).open("r", encoding="utf-8") as input_file:
        data = json.load(input_file)

    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")

    records: list[StartupRecord] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(f"{path} contains a non-object record")
        records.append(_clean_record(item))
    return records


def _flatten(sources: Iterable[list[StartupRecord]]) -> Iterable[StartupRecord]:
    for source in sources:
        for record in source:
            yield record


def _clean_record(record: dict) -> StartupRecord:
    return {
        "name": _clean_text(str(record.get("name", ""))),
        "one_liner": _clean_text(str(record.get("one_liner", ""))),
        "tags": _clean_tags(record.get("tags", [])),
        "website": _clean_text(str(record.get("website", ""))),
        "source": _clean_text(str(record.get("source", ""))),
    }


def _clean_tags(tags: object) -> list[str]:
    if not isinstance(tags, list):
        return []

    clean: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        text = _clean_text(str(tag))
        key = _normalize_name(text)
        if not key or key in seen:
            continue
        seen.add(key)
        clean.append(text)
    return clean


def _dedupe_key(record: StartupRecord) -> str:
    website_key = _normalize_website(record["website"])
    if website_key:
        return f"website:{website_key}"

    name_key = _normalize_name(record["name"])
    if name_key:
        return f"name:{name_key}"

    return ""


def _normalize_website(website: str) -> str:
    value = website.strip()
    if not value:
        return ""

    if "://" not in value:
        value = "https://" + value

    parsed = urlparse(value)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    return f"{host}{path}"


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
