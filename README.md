Startup Radar

Startup Radar is a live startup discovery tool. It aggregates fresh startups from Y Combinator, Product Hunt, and BetaList into one browsable grid, and generates an on-demand, synthesized profile for whichever one you click on — summary, news, founders, funding signal, hiring status, contact info, and GitHub open-source activity, scored against a fixed skill profile so you can spot the ones worth working at or contributing to.

**Features**

- Combined grid of startups pulled from three sources: YC, Product Hunt, BetaList
- Search, filter by source/tag, and sort by relevance
- Click-to-synthesize detail panel: summary, recent news, founders, funding info, hiring signal, contact details
- GitHub lookup per startup: repo URL, stars, primary language, open "good first issue" count
- Relevance scoring (High/Medium/Low) against a fixed skill profile (distributed systems, Go, Kafka, cloud infra, backend, AWS, developer tools, open source)
- Graceful fallbacks everywhere — mock data on the frontend if the API is unreachable, plain HTTP scraping on the backend if Bright Data isn't configured, "not found" instead of errors for missing detail fields

**Architecture**

- Two-tier design: a cheap bulk scrape builds the browsable grid once (`data/startups.json`); the expensive work — live web search, GitHub lookups, founder/funding extraction — only runs when a startup is clicked
- Scraping and search are done through Bright Data; open-source signal comes from the GitHub REST API
- Flask API (`app/main.py`, port 8000) sits between the scraped/synthesized data and the frontend, with two routes: `/api/detail` and `/api/health`
- React frontend (Vite dev server) proxies `/api/*` calls to the Flask backend, so no CORS handling is needed locally

**Tech stack**

- Backend: Python, Flask + flask-cors, requests, python-dotenv
- Scraping: Bright Data (site fetch + Google SERP search), stdlib `urllib`/`html.parser` as a no-key fallback for BetaList
- Frontend: React 19, Vite 6, plain JSX, `lucide-react` for icons, hand-written CSS (no Tailwind, no component library)
- Data store: flat JSON file (`data/startups.json`), no database

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

**Running it locally**

Backend:
```
pip install -r requirements.txt
python app/main.py
```
Runs the Flask API on http://127.0.0.1:8000.

Frontend:
```
npm install
npm run dev
```
Runs the Vite dev server and proxies `/api/*` to the Flask backend.

To regenerate `data/startups.json` from all three sources:
```
python -c "from scrapers.merge import merge_sources, write_startups; write_startups(merge_sources())"
```

Tests:
```
python -m unittest tests/test_person2.py
```

**Environment variables**

Copy `.env.example` to `.env`:
```
BRIGHTDATA_API_TOKEN=your_token_here
BRIGHTDATA_ZONE=startup_radar_web_unlocker
```
- Bright Data is optional — without it, scraping and detail lookups fall back to plain HTTP requests / DuckDuckGo search, and the frontend falls back to mock data.
- `GITHUB_TOKEN` is also optional — raises the GitHub API rate limit for the open-source lookups.
