"""
schema.py — the shared contract for the whole team.

Every scraper, every detail function, and the frontend all read/write
data shaped exactly like this. Nobody changes this file alone — if a
field needs to change, say so in the group chat first, since everyone's
code depends on it.
"""

from typing import TypedDict, Optional


class StartupRecord(TypedDict):
    """
    One row in the browse grid. This is what Person 1 and Person 2's
    scrapers must return, one of these per startup they find.
    """
    name: str            # "Stripe"
    one_liner: str        # "Online payment processing for internet businesses"
    tags: list[str]        # ["fintech", "developer tools"]
    website: str           # "https://stripe.com"
    source: str             # "YC" | "ProductHunt" | "BetaList"


class GithubInfo(TypedDict):
    """
    What Person 3's GitHub lookup returns. If a startup has no public
    GitHub org, every field here is None — that's expected, not an error.
    """
    repo_url: Optional[str]                  # "https://github.com/stripe/stripe-python"
    stars: Optional[int]                      # 2400
    primary_language: Optional[str]            # "Python"
    good_first_issue_count: Optional[int]       # 3
    last_commit_date: Optional[str]              # "2026-07-01"


class StartupDetail(TypedDict):
    """
    What shows up in the detail panel when someone clicks a startup card.
    This is what Person 3's get_startup_detail() must return.

    Every field here is found the SAME way regardless of which source
    the startup came from (YC, Product Hunt, BetaList, etc.) — nothing
    is source-specific. If a field can't be found, use the "not found"
    values below instead of omitting the field or crashing.
    """
    name: str                  # "Stripe"
    summary: str                 # 2-3 sentence synthesized description
    news: list[str]               # up to 3 short headline strings, [] if none found
    hiring_signal: str              # "hiring" | "unclear" | "no signal found"
    founders: list[str]              # names found on an About/Team page or via search,
                                       # [] if not publicly listed (very common for small startups)
    funding_summary: str               # 1-2 sentence synthesized funding signal from search,
                                         # "no funding information found" if nothing turns up
    contact: Optional[str]              # public contact page URL or general email
                                          # (info@/hello@), None if neither is published
    github: GithubInfo