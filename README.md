Startup Radar

Most startup lists go stale the moment they're scraped. Startup Radar keeps browsing cheap and pushes the expensive work to the moment you actually care: click a company and it synthesizes a live profile on the spot — summary, recent news, founders, funding signal, hiring status, contact info, and GitHub activity — then scores it against a fixed skill profile so you can tell at a glance whether it's worth pursuing.

Quick start
```
pip install -r requirements.txt
python app/main.py          # Flask API on http://127.0.0.1:8000

npm install
npm run dev                 # Vite dev server, proxies /api/* to Flask
```
No API keys required to try it — without Bright Data configured, everything falls back to plain HTTP scraping, and the frontend falls back to bundled mock data if the API or dataset isn't reachable.

**Features**

- One grid, three sources — startups pulled from Y Combinator, Product Hunt, and BetaList, deduped by website
- Search, filter by source or tag, and sort by relevance
- Click a card, get a synthesized profile: summary, recent news, founders, funding signal, hiring status, contact details
- GitHub signal per startup — repo URL, stars, primary language, open "good first issue" count
- Relevance scoring (High / Medium / Low) against a fixed skill profile: distributed systems, Go, Kafka, cloud infra, backend, AWS, developer tools, open source
- Never a blank screen — missing data resolves to "not found" rather than an error, and the UI degrades to mock data if the backend is down

**How it works**

1. Scrape once, cheaply — `scrapers/yc.py`, `producthunt.py`, and `betalist.py` each pull a batch of startups, and `merge.py` dedupes and writes the result to `data/startups.json`. This is what the grid renders — fast, no live calls per card.
2. Browse for free — the React app reads that JSON directly, so scrolling and filtering the grid costs nothing.
3. Synthesize on click — picking a startup calls `/api/detail`, which fetches the company's site, runs a search for news/funding/hiring, and looks up its GitHub org, then merges all of that into one profile in real time.

This split is the whole point: bulk data stays cheap and fast, and the expensive, high-signal lookups only ever run for the one startup you're actually looking at.

**API**

`GET /api/health` — `{"status": "ok"}`

`GET /api/detail?name=Stripe&website=https://stripe.com` — returns a synthesized profile shaped like:
```json
{
  "name": "Stripe",
  "summary": "Online payment processing for internet businesses.",
  "news": ["Stripe launches new billing API", "..."],
  "hiring_signal": "hiring",
  "founders": ["Patrick Collison", "John Collison"],
  "funding_summary": "Raised Series I at a $95B valuation.",
  "contact": "https://stripe.com/contact",
  "github": {
    "repo_url": "https://github.com/stripe/stripe-python",
    "stars": 2400,
    "primary_language": "Python",
    "good_first_issue_count": 3,
    "last_commit_date": "2026-07-01"
  }
}
```

**Tech stack**

- Backend: Python, Flask + flask-cors, requests, python-dotenv
- Scraping & search: Bright Data (site fetch + Google SERP), with a stdlib `urllib`/`html.parser` fallback for BetaList that needs no key at all
- Frontend: React 19, Vite 6, plain JSX, `lucide-react` icons, hand-written CSS — no Tailwind, no component library
- Data store: a flat JSON file (`data/startups.json`) — no database

**Project layout**

```
app/main.py            Flask API — /api/detail, /api/health
app/relevance.py        server-side relevance scoring
scrapers/yc.py           YC scraper
scrapers/producthunt.py  Product Hunt scraper
scrapers/betalist.py     BetaList scraper
scrapers/merge.py        dedupe + write data/startups.json
detail/web_detail.py     summary, founders, hiring, funding, contact
detail/github_detail.py  GitHub repo lookup + good-first-issue count
detail/synthesis.py      combines web + GitHub into one detail payload
schema.py                shared data shapes (StartupRecord, GithubInfo, StartupDetail)
data/startups.json       the scraped, merged dataset the grid reads
src/main.jsx             the React app (grid + detail panel)
src/lib/relevance.js     client-side relevance scoring
src/data/mockStartups.js fallback demo data
tests/test_person2.py    scraper + merge tests
```

**Regenerating the dataset**
```
python -c "from scrapers.merge import merge_sources, write_startups; write_startups(merge_sources())"
```

**Tests**
```
python -m unittest tests/test_person2.py
```

**Environment variables**

Copy `.env.example` to `.env`:
```
BRIGHTDATA_API_TOKEN=your_token_here
BRIGHTDATA_ZONE=startup_radar_web_unlocker
```
- `BRIGHTDATA_*` — optional. Without it, scraping and detail lookups fall back to plain HTTP requests and DuckDuckGo search instead of Bright Data's unlocker and SERP API.
- `GITHUB_TOKEN` — optional. Raises the GitHub API rate limit for the open-source lookups.
