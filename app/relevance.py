"""Explainable startup relevance scoring for Person 4.

The React app mirrors this same logic in ``src/lib/relevance.js``. Keeping the
Python version here gives the rest of the team a stable integration point if
they want to pre-score generated startup records later.
"""

from __future__ import annotations

from typing import Any


# Derived from actual tag frequency across data/startups.json (top 8 tags
# covering the widest real spread), not an arbitrary example list -- this
# is what makes "sort by relevance" produce a meaningful High/Medium/Low
# mix instead of everything landing on the same bucket.
SKILL_PROFILE = [
    "saas",
    "productivity",
    "b2b",
    "api",
    "fintech",
    "automation",
    "developer tools",
    "artificial intelligence",
]


def score_startup(startup: dict[str, Any], detail: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return an explainable High/Medium/Low relevance score.

    The score is keyword overlap against browse tags, the one-liner, source,
    optional hiring text, and optional GitHub primary language.
    """

    detail = detail or {}
    github = detail.get("github") or {}
    searchable_parts = [
        startup.get("name"),
        startup.get("one_liner"),
        startup.get("source"),
        *(startup.get("tags") or []),
        detail.get("hiring_signal"),
        github.get("primary_language"),
    ]
    haystack = " ".join(str(part) for part in searchable_parts if part).lower()
    matches = [keyword for keyword in SKILL_PROFILE if keyword.lower() in haystack]
    score = len(matches)

    if score >= 3:
        label = "High"
    elif score >= 1:
        label = "Medium"
    else:
        label = "Low"

    return {"score": score, "matches": matches, "label": label}
