"""
Synthesis layer for the startup detail panel.

The public function in this module is the integration point Person 4 can call
from the Streamlit detail view.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from schema import GithubInfo, StartupDetail

from detail.github_detail import get_github_data
from detail.web_detail import get_web_detail


def _empty_github_info() -> GithubInfo:
    return {
        "repo_url": None,
        "stars": None,
        "primary_language": None,
        "good_first_issue_count": None,
        "last_commit_date": None,
    }


def _safe_string(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _safe_string_list(value: Any, limit: int | None = None) -> list[str]:
    if not isinstance(value, list):
        return []
    strings = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return strings[:limit] if limit is not None else strings


def _safe_github_info(value: Any) -> GithubInfo:
    if not isinstance(value, dict):
        return _empty_github_info()
    return {
        "repo_url": value.get("repo_url") if isinstance(value.get("repo_url"), str) else None,
        "stars": value.get("stars") if isinstance(value.get("stars"), int) else None,
        "primary_language": value.get("primary_language") if isinstance(value.get("primary_language"), str) else None,
        "good_first_issue_count": (
            value.get("good_first_issue_count")
            if isinstance(value.get("good_first_issue_count"), int)
            else None
        ),
        "last_commit_date": value.get("last_commit_date") if isinstance(value.get("last_commit_date"), str) else None,
    }


def get_startup_detail(name: str, website: str) -> StartupDetail:
    """
    Build the complete StartupDetail contract for any startup source.

    This function deliberately does not accept or branch on source. The same
    live-detail logic applies to YC, Product Hunt, BetaList, and future
    sources that provide a name and website.
    """
    clean_name = name.strip() or "Unknown startup"

    with ThreadPoolExecutor(max_workers=2) as pool:
        web_future = pool.submit(get_web_detail, clean_name, website)
        github_future = pool.submit(get_github_data, clean_name)

        try:
            web_detail = web_future.result()
        except Exception:
            web_detail = {}

        try:
            github = github_future.result()
        except Exception:
            github = _empty_github_info()

    contact = web_detail.get("contact") if isinstance(web_detail, dict) else None
    return {
        "name": clean_name,
        "summary": _safe_string(
            web_detail.get("summary") if isinstance(web_detail, dict) else None,
            f"No live website summary found for {clean_name}.",
        ),
        "news": _safe_string_list(web_detail.get("news") if isinstance(web_detail, dict) else None, limit=3),
        "hiring_signal": _safe_string(
            web_detail.get("hiring_signal") if isinstance(web_detail, dict) else None,
            "no signal found",
        ),
        "founders": _safe_string_list(web_detail.get("founders") if isinstance(web_detail, dict) else None),
        "funding_summary": _safe_string(
            web_detail.get("funding_summary") if isinstance(web_detail, dict) else None,
            "no funding information found",
        ),
        "contact": contact.strip() if isinstance(contact, str) and contact.strip() else None,
        "github": _safe_github_info(github),
    }
