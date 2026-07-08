# Startup Radar — Implementation Plan

**One-line pitch:** A live, agentic startup discovery tool that aggregates startups — big and small, not just the well-known YC ones — into one place. Browse a list at a glance, then click into any startup for a real-time synthesized profile (recent news, hiring status, and a direct link to contribute to their open source), ranked by relevance to your own skillset.

**Built for:** AWS Builder's Loft hackathon (Bright Data + Codex track)
**Time budget:** 4 hours
**Team size:** 4 people

---

## 1. Verified facts this plan relies on

Everything below was checked before writing this plan, so the team isn't building on guesses:

- **YC directory** is publicly accessible at `ycombinator.com/companies`, and industry-filtered pages exist at URLs like `ycombinator.com/companies/industry/{industry}` (e.g. `.../industry/enterprise`, `.../industry/monitoring`, `.../industry/search`). These pages return real, scrapeable listing text — confirmed by direct fetch.
- **GitHub REST API** (no scraping needed) supports:
  - `GET api.github.com/orgs/{org}/repos` — list an org's public repos
  - `GET api.github.com/search/repositories?q=...` — search repos by keyword/org/language
  - `GET api.github.com/search/issues?q=repo:{owner}/{repo}+label:"good first issue"+state:open` — count open beginner-friendly issues
  - Unauthenticated requests are rate-limited to 60/hour; a free personal access token raises this to 5,000/hour — get one before the hackathon starts.
- **Bright Data MCP** exposes `search_engine`, `scrape_as_markdown`, `scrape_as_html`, and browser-automation tools (`scraping_browser_navigate`, `scraping_browser_click`, etc.) through an API-token-based setup, with a free tier of 5,000 monthly credits (base tools cost 1 credit/request).

### Not yet verified — verify live in the first 15 minutes
- **Product Hunt** and **BetaList** page structures were **not verified** in this research pass. Before committing Person 1/2's time to them, the team should do a quick live check (open the site, try one `scrape_as_markdown` call, look for a JSON endpoint in the browser Network tab) and confirm the listing structure is scrapeable the same way YC's is. If either site turns out to be heavily JS-rendered or blocks scraping, swap it for another public, scrape-friendly small-startup directory (Indie Hackers is a reasonable fallback) rather than losing time fighting one site.
- Treat this verification as **step 0** of Person 1 and Person 2's work, not an assumption baked into the plan.

---

## 2. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Streamlit (fallback: minimal Next.js if time allows) | Fastest path to a working UI in 4 hours; no need to hand-roll state management |
| Backend | Python | Bright Data MCP and the GitHub API both have clean Python clients; Codex scaffolds Python quickly |
| Data store | JSON files (no DB) | Zero setup time; bulk scrape writes once, detail view is generated live |
| Web data | Bright Data MCP (`search_engine`, `scrape_as_markdown`, browser tools as fallback) | Handles anti-bot/JS-rendered pages without building scraping infra from scratch |
| Open-source data | GitHub REST API (direct, not via Bright Data) | Free, structured JSON, reliable rate limits with a token |
| Code generation | Codex | Scaffolds scrapers, synthesis logic, and UI shell so team time goes to wiring and demo polish |

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                BULK LAYER (once, multi-source)                 │
│  scrape_yc()          → standard record shape  ─┐              │
│  scrape_producthunt() → standard record shape  ─┼─► merge +    │
│  scrape_betalist()    → standard record shape  ─┘   dedupe     │
│                                                   → startups.json│
│  Standard fields: name, one_liner, tags, website, source        │
│  A new source later = one more scrape_*() function returning    │
│  the same shape — nothing downstream changes                    │
└───────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                 BROWSE VIEW (Streamlit grid)                   │
│  Filter by tag/source, search by name, "sort by relevance" toggle│
└───────────────────────────┬────────────────────────────────┘
                             │ user clicks a startup
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                DETAIL LAYER (on-demand, live)                  │
│  1. Bright Data: scrape company website → mission/product        │
│     + About/Team page → founders + Contact page → contact info    │
│  2. Bright Data: search_engine("{company} news") → headlines      │
│  3. Bright Data: search_engine("{company} careers") → hiring       │
│     signal (soft; fallback if career page is JS-rendered)          │
│  4. Bright Data: search_engine("{company} funding raised") →        │
│     funding summary (soft signal)                                    │
│  5. Bright Data: search_engine("{company} founder") → fallback if     │
│     no team page exists                                                │
│  6. GitHub API: search org/repos → stars, language, open                │
│     "good first issue" count, last commit                                │
│  → synthesis step compiles all of this into one profile dict              │
│  Same logic for every startup regardless of source (YC/PH/BetaList)        │
└───────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                 DETAIL VIEW (Streamlit panel)                  │
│  Synthesized summary + founders + news + funding + hiring badge  │
│  + contact info + "Contribute here"                                │
└─────────────────────────────────────────────────────────────┘
```

The two-tier design (cheap bulk scrape for browsing, expensive live synthesis only on click) is the core architectural idea worth calling out to judges — it's what makes this feel like a product instead of a static scraped dataset.

---

## 4. Shared Data Contract (`schema.py`)

Agree on this as a group in the first 15 minutes, write it as actual code, and treat it as frozen unless the whole team agrees to a change. **Every field here is found the same way regardless of which source the startup came from** — no field is specific to YC, Product Hunt, or BetaList, so the detail logic doesn't need to branch by source:

```python
from typing import TypedDict, Optional

class StartupRecord(TypedDict):
    name: str
    one_liner: str
    tags: list[str]
    website: str
    source: str          # "YC" | "ProductHunt" | "BetaList" | ...

class GithubInfo(TypedDict):
    repo_url: Optional[str]
    stars: Optional[int]
    primary_language: Optional[str]
    good_first_issue_count: Optional[int]
    last_commit_date: Optional[str]

class StartupDetail(TypedDict):
    name: str
    summary: str                 # synthesized from site scrape
    news: list[str]               # up to 3 short headline strings, [] if none found
    hiring_signal: str              # "hiring" | "unclear" | "no signal found"
    founders: list[str]              # from About/Team page or search fallback, [] if not listed
    funding_summary: str               # synthesized from search, "no funding information found" if none
    contact: Optional[str]              # public contact page URL or general email, None if neither exists
    github: GithubInfo
```

If a field can't be found (no news, no GitHub repo, no team page, etc.), use `None`/empty list/the specified "not found" string rather than omitting the field or crashing — every consumer of this data should treat missing info as a normal, expected state, not an error.

---

## 5. Repository Structure

```
startup-radar/
├── data/
│   └── startups.json          ← generated file, not hand-edited by anyone
├── scrapers/
│   ├── yc.py                  ← Person 1
│   ├── producthunt.py         ← Person 1
│   ├── betalist.py            ← Person 2
│   └── merge.py               ← Person 2
├── detail/
│   ├── web_detail.py          ← Person 3
│   ├── github_detail.py       ← Person 3
│   └── synthesis.py           ← Person 3
├── app/
│   ├── main.py                ← Person 4 (only integration point)
│   ├── ui_grid.py              ← Person 4
│   ├── ui_detail.py            ← Person 4
│   └── relevance.py            ← Person 4
├── schema.py                  ← the shared contract (§4), frozen after minute 15
└── README.md
```

**Why this avoids merge conflicts:** each person's files live in their own folder. Nobody else edits those files, so Git has nothing to fight over. The only shared file is `schema.py`, and it's written once, together, before anyone starts coding.

---

## 6. Use of Bright Data — explicit call list

| Call | Tool | Tier | Owner |
|---|---|---|---|
| YC directory listing | `scrape_as_markdown` (fallback `scrape_as_html`) | Bulk, once | Person 1 |
| Product Hunt listings | `scrape_as_markdown` (verify structure first — see §1) | Bulk, once | Person 1 |
| BetaList listings | `scrape_as_markdown` (verify structure first — see §1) | Bulk, once | Person 2 |
| Company website content | `scrape_as_markdown` — mission/product | Detail, on click | Person 3 |
| Company About/Team page | `scrape_as_markdown` — founder names, if a team page exists | Detail, on click | Person 3 |
| Company Contact page | `scrape_as_markdown` — contact URL or general email | Detail, on click | Person 3 |
| Recent news | `search_engine` | Detail, on click | Person 3 |
| Hiring signal | `search_engine`, fallback if career page is JS-rendered/Greenhouse-embedded | Detail, on click | Person 3 |
| Funding signal | `search_engine("{company} funding raised")` | Detail, on click | Person 3 |
| Founders (fallback) | `search_engine("{company} founder")`, only if no team page was found | Detail, on click | Person 3 |

This is deliberately the same set of calls for every startup no matter which bulk source it came from — nothing here is YC-specific, Product-Hunt-specific, etc.

Demo line worth using: *"Bright Data handles the parts of the web that fight back — bot detection, JS rendering — so the detail view can synthesize fresh instead of relying on a stale cache."*

**Cost check:** free tier gives 5,000 credits/month, base tool calls cost 1 credit each. Bulk scrape (a handful of calls) plus detail views on even 30-40 companies during build/testing stays well under that. Avoid `PRO_MODE` and go easy on browser-automation calls (used only if infinite-scroll pagination requires it) since those are the more expensive path.

---

## 7. Use of Codex

Hand off the boilerplate-heavy, clearly-specified pieces:
- Scaffold each `scrape_*()` function (pagination, JSON writer) once the target site's structure is confirmed
- Scaffold the GitHub API client (search org, list repos, filter/sort)
- Write the synthesis function that takes the 4 raw detail sources and compiles them into `StartupDetail` — good to hand off since the input/output shape is already fixed in `schema.py`
- Scaffold the Streamlit UI shell (grid + detail panel + loading states)

Keep personal ownership of: the relevance-scoring logic (§8) and the demo narrative — these are what judges will probe on, so understand them deeply rather than letting Codex fully own them.

---

## 8. Relevance Filtering (differentiator)

Simple, explainable scoring — don't overbuild:
- Define a fixed skill profile as keywords: e.g. `distributed systems, Go, Kafka, cloud infra, backend, AWS`
- Score each startup by keyword overlap against: its tags, its GitHub repo's primary language, and its hiring-signal text (when present)
- Surface as a "Relevance: High / Medium / Low" badge or sort order — not a black-box score, since it needs to be explainable live

Demo close: toggle "sort by relevance to me" and show it re-ranking to surface startups worth working at or contributing to.

---

## 9. Data Availability Summary

| Field | Reliability | Source |
|---|---|---|
| Name, one-liner, tags | High | Bulk scrape (each source) |
| Company mission/product description | High | Company site scrape |
| Contact info (public email/contact page) | High | Company site scrape |
| Open-source repo + contribution stats | High | GitHub API |
| Recent news | Medium — varies by company visibility | `search_engine` |
| Funding signal | Medium — varies by company visibility, no precise amounts guaranteed | `search_engine` |
| Hiring signal | Medium-low — JS-heavy career pages | `search_engine` fallback |
| Founders | Medium-low — many small startups don't publish a team page | Company About/Team page, `search_engine` fallback |
| Precise funding amounts | Not reliable — don't promise this | N/A (funding_summary is a soft signal, not exact figures) |

Every medium/low field must degrade gracefully in the UI — "no significant recent news found," "no funding information found," and an empty founders list are all valid states, not crashes.

---

## 10. Functional View (what the judges see)

1. **Browse screen** — grid of startup cards (name, one-liner, tags, source badge), filter by tag/source, "sort by relevance to me" toggle
2. **Click a card** → detail panel loads live with a visible loading state ("fetching live data…")
3. **Detail panel shows** — synthesized 2-3 sentence summary, founders (if found), recent news snippet(s), funding signal, hiring status badge, contact link, and a "Contribute here" section with top repo, open good-first-issue count, and a direct link
4. **Closing demo beat** — toggle relevance sort, click into a high-relevance match, show the contribute link: "this is a startup I could start contributing to today"

---

## 11. Team Split (4 people)

**Step 0, together, first 15 minutes:**
1. Live-check Product Hunt and BetaList page structure (see §1) — confirm or swap sources
2. Write and freeze `schema.py` together

### Person 1 — Bulk source scrapers (YC + Product Hunt)
**Do:**
- Write `scrape_yc(filters) → list[StartupRecord]` using `scrape_as_markdown` on the YC directory
- Write `scrape_producthunt() → list[StartupRecord]`, same pattern, once structure is confirmed in Step 0
**Independent of:** everyone — only needs the frozen `schema.py` to start
**Blocks:** Person 2's merge step needs these two functions' *output shape* (already fixed by the contract) to build against — not the finished functions

### Person 2 — Bulk source scraper (BetaList) + merge/dedupe
**Do:**
- Write `scrape_betalist() → list[StartupRecord]`, once structure is confirmed in Step 0
- Write `merge_sources(list1, list2, list3) → startups.json`: concatenate + dedupe by name/website
**Independent of:** Person 1's actual scrapers — build and test the merge function against hand-written fake records matching `schema.py`, swap in real output later
**Blocks:** Person 4 needs the final `startups.json` for the browse grid (can use sample data until it lands)

### Person 3 — Detail synthesis + GitHub integration
**Do:**
- Write `get_web_detail(name, website) → dict`: Bright Data calls for company site scrape (mission/product), About/Team page (founders), Contact page (contact info), news search, careers search, and funding search
- Write `get_github_data(name) → GithubInfo`: GitHub API org/repo lookup, stars, language, open good-first-issue count
- Combine both into `get_startup_detail(name, website) → StartupDetail`
- Keep every lookup generic — the same function runs for a YC startup, a Product Hunt startup, or any future source, with no source-specific branching
**Independent of:** everyone — build and test entirely against one hardcoded sample startup (e.g. a well-known company with a public GitHub org, to avoid burning time on an obscure name with no data)
**Blocks:** Person 4's detail panel needs this function's output shape — already fixed in `schema.py`, so Person 4 can build in parallel without waiting

### Person 4 — Frontend + relevance scoring
**Do:**
- Build the Streamlit grid view (filter/search/sort) reading from `startups.json`
- Build the detail panel that calls `get_startup_detail()` on click, with a loading state
- Write relevance scoring (§8): keyword overlap between the fixed skill profile and each startup's tags/repo language/hiring text
**Independent of:** starts immediately using hand-written mock data matching both contracts in `schema.py`
**Depends on:** swaps mock data for Person 2's real `startups.json` and Person 3's real `get_startup_detail()` once those land — plan this swap for the hour 2-3 mark, not as something built into the UI logic from scratch

### Dependency summary
- Nothing blocks anyone from **starting** — the frozen schema removes all hard blockers
- The only real dependency: Person 4's final wiring needs Person 2's merged JSON and Person 3's detail function — a swap-in at hour 2-3, not a from-scratch build
- Persons 1, 2, and 3 are otherwise fully parallel and don't depend on each other at all

---

## 12. Git Workflow

- Shared repo, one branch per person, matching the folder each person owns (§5)
- Commit and push every 20-30 minutes, not one big commit at the end
- Merge into `main` every 45-60 minutes rather than waiting until the end
- `data/startups.json` is a generated artifact, never hand-edited — if two people regenerate it, last-write-wins is fine
- If `schema.py` needs a field added mid-hackathon, announce it to the group before editing — it's the one file everyone depends on, so a silent change breaks other people's code, not just causes a merge conflict

---

## 13. Build Order (stop-anywhere checkpoints)

1. Step 0 verification (Product Hunt/BetaList structure) + frozen `schema.py` (must-have, blocks nothing but should happen first)
2. Bulk scrape (YC + Product Hunt + BetaList) → merged `startups.json` (foundation, must-have)
3. GitHub API integration (strongest differentiator, cheap)
4. Company site + news synthesis (solid mid-tier)
5. Relevance scoring + browse UI
6. Hiring signal via search fallback

Each numbered step is independently demoable — if the team runs out of time at step 5, there's still a complete, honest story to show.

---

## 14. Final Integration Window (last 30-45 minutes, whole team)

- Wire Person 2's real `startups.json` and Person 3's real `get_startup_detail()` into Person 4's app, replacing mock data
- Run through the full demo flow once, end to end, before presenting
- Cut anything flaky (a source that's returning bad data, a slow call, a field that keeps erroring) rather than debugging it live — a smaller, reliable demo beats a bigger, broken one
