"""
Shared low-level Bright Data caller used by yc.py and producthunt.py (Person 1).

Verified live against the real Bright Data account before this was written:
POST https://api.brightdata.com/request with a JSON body of
{"zone": ..., "url": ..., "format": "raw", "data_format": "markdown"}
returns the page's rendered content converted to markdown, handling
JS-rendered pages (confirmed: a plain requests.get() of the YC directory
returns only an empty Inertia/Vite app shell with no company data --
Bright Data's headless-browser-backed unlocker is what actually renders it).
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

_API_URL = "https://api.brightdata.com/request"
_TOKEN = os.environ.get("BRIGHTDATA_API_TOKEN")
_ZONE = os.environ.get("BRIGHTDATA_ZONE", "startup_radar_web_unlocker")


class BrightDataError(RuntimeError):
    pass


def fetch_markdown(url: str, timeout: int = 60) -> str:
    """Fetch a URL through Bright Data's Web Unlocker and return it as markdown."""
    if not _TOKEN or _TOKEN == "your_token_here":
        raise BrightDataError(
            "BRIGHTDATA_API_TOKEN is not set. Copy .env.example to .env and "
            "fill in a real token from https://brightdata.com/cp/setting/users"
        )

    try:
        response = requests.post(
            _API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_TOKEN}",
            },
            json={"zone": _ZONE, "url": url, "format": "raw", "data_format": "markdown"},
            timeout=timeout,
        )
    except requests.exceptions.RequestException as e:
        # Network-level failures (timeouts, connection resets, etc.) are just
        # as common as bad HTTP statuses under real load -- both must degrade
        # gracefully the same way, not crash the whole scrape run.
        raise BrightDataError(f"Bright Data request for {url} failed: {e}") from e

    if response.status_code != 200:
        raise BrightDataError(
            f"Bright Data request for {url} failed: HTTP {response.status_code} {response.text[:300]}"
        )
    return response.text
