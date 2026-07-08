"""
GitHub lookup helpers for the startup detail panel.

This module intentionally uses only the Python standard library so the
hackathon demo does not depend on installing extra packages. All network
failures degrade to the empty GithubInfo shape from schema.py.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from schema import GithubInfo


GITHUB_API = "https://api.github.com"
TIMEOUT_SECONDS = 8


def _empty_github_info() -> GithubInfo:
    return {
        "repo_url": None,
        "stars": None,
        "primary_language": None,
        "good_first_issue_count": None,
        "last_commit_date": None,
    }


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _slug_candidates(name: str) -> list[str]:
    normalized_words = re.findall(r"[a-z0-9]+", name.lower())
    if not normalized_words:
        return []

    joined = "".join(normalized_words)
    hyphenated = "-".join(normalized_words)
    underscored = "_".join(normalized_words)

    candidates = [joined, hyphenated, underscored]
    if len(normalized_words) > 1:
        candidates.append(normalized_words[0])

    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique[:4]


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Startup-Radar",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(path: str, params: dict[str, Any] | None = None) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    request = Request(f"{GITHUB_API}{path}{query}", headers=_github_headers())

    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _repo_score(repo: dict[str, Any], name: str) -> tuple[int, int]:
    target = _normalize(name)
    owner = _normalize(repo.get("owner", {}).get("login", ""))
    repo_name = _normalize(repo.get("name", ""))
    full_name = _normalize(repo.get("full_name", ""))

    score = 0
    if target and owner == target:
        score += 50
    if target and repo_name == target:
        score += 35
    if target and target in owner:
        score += 20
    if target and target in repo_name:
        score += 15
    if target and target in full_name:
        score += 10
    if repo.get("archived") is False:
        score += 4
    if repo.get("fork") is False:
        score += 8

    return score, int(repo.get("stargazers_count") or 0)


def _best_repo_from_org(slug: str, name: str) -> dict[str, Any] | None:
    repos = _request_json(f"/orgs/{slug}/repos", {"per_page": 30, "sort": "updated"})
    if not isinstance(repos, list) or not repos:
        return None

    public_repos = [repo for repo in repos if isinstance(repo, dict) and not repo.get("fork")]
    if not public_repos:
        public_repos = [repo for repo in repos if isinstance(repo, dict)]

    return max(public_repos, key=lambda repo: _repo_score(repo, name), default=None)


def _best_repo_from_search(name: str) -> dict[str, Any] | None:
    results = _request_json(
        "/search/repositories",
        {
            "q": f"{name} in:name,description",
            "sort": "stars",
            "order": "desc",
            "per_page": 10,
        },
    )
    items = results.get("items") if isinstance(results, dict) else None
    if not isinstance(items, list) or not items:
        return None

    repos = [repo for repo in items if isinstance(repo, dict) and not repo.get("fork")]
    if not repos:
        repos = [repo for repo in items if isinstance(repo, dict)]

    return max(repos, key=lambda repo: _repo_score(repo, name), default=None)


def _good_first_issue_count(full_name: str) -> int | None:
    results = _request_json(
        "/search/issues",
        {"q": f'repo:{full_name} label:"good first issue" state:open', "per_page": 1},
    )
    if not isinstance(results, dict):
        return None
    total_count = results.get("total_count")
    return total_count if isinstance(total_count, int) else None


def get_github_data(name: str) -> GithubInfo:
    """
    Return likely open-source contribution info for a startup.

    The lookup first tries organization slugs derived from the company name,
    then falls back to GitHub repository search. Any failed or inconclusive
    lookup returns the complete empty GithubInfo shape.
    """
    clean_name = name.strip()
    if not clean_name:
        return _empty_github_info()

    repo: dict[str, Any] | None = None
    for slug in _slug_candidates(clean_name):
        repo = _best_repo_from_org(slug, clean_name)
        if repo:
            break

    if not repo:
        repo = _best_repo_from_search(clean_name)

    if not repo:
        return _empty_github_info()

    full_name = repo.get("full_name")
    pushed_at = repo.get("pushed_at")
    return {
        "repo_url": repo.get("html_url"),
        "stars": repo.get("stargazers_count") if isinstance(repo.get("stargazers_count"), int) else None,
        "primary_language": repo.get("language"),
        "good_first_issue_count": _good_first_issue_count(full_name) if isinstance(full_name, str) else None,
        "last_commit_date": pushed_at[:10] if isinstance(pushed_at, str) and len(pushed_at) >= 10 else None,
    }
