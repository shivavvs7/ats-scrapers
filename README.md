# jobhive

> **The open dataset and toolkit for global job market data.**
> 1M+ jobs from 16 000+ companies, scraped directly from ATS sources — no LinkedIn, no reposts, no recruiters.

[![PyPI](https://img.shields.io/pypi/v/jobhive.svg)](https://pypi.org/project/jobhive/)
[![Python](https://img.shields.io/pypi/pyversions/jobhive.svg)](https://pypi.org/project/jobhive/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

```python
from jobhive import search

df = search(query="ml engineer", location="Paris", remote=True)
```

That's it. No API key, no auth, no rate limits. The dataset lives on
Cloudflare R2 and updates every 24 hours.

---

## Why jobhive

LinkedIn job scrapers break every quarter. Indeed mirrors are full of
duplicates and ghost listings. **jobhive goes one layer down**: directly to
the ATS platforms (Greenhouse, Lever, Ashby, Workday, etc.) where companies
actually post jobs first.

- **Single source of truth** — every posting comes from the company's own
  ATS, so titles, locations, and salaries are accurate.
- **No duplicates** — one ATS posting = one row.
- **Salary data when it exists** — Ashby, Greenhouse Pay Transparency, and
  others ship structured comp ranges; we expose them as typed fields.
- **MIT licensed, fully open** — fork the dataset, fork the scrapers, run
  your own pipeline.
- **Reverse-engineered, not brittle** — every scraper was built by capturing
  the ATS's own network traffic with
  [reverse-api-engineer](https://github.com/kalil0321/reverse-api-engineer),
  so we hit the same JSON endpoints the official UI uses. No HTML parsing,
  no Playwright, no breakage on every redesign.

## Coverage (May 2026)

| ATS | Jobs | Companies |
|---|---:|---:|
| Workday | 381 022 | 1 870 |
| SmartRecruiters | 204 072 | 811 |
| Greenhouse | 129 617 | 2 749 |
| Workable | 100 196 | 3 971 |
| Lever | 67 938 | 1 790 |
| Ashby | 32 563 | 1 813 |
| Rippling | 18 996 | 1 503 |
| Avature | 13 732 | 69 |
| Personio | 6 504 | 964 |
| Join.com | 600 | 146 |
| **Total** | **~955 000+** | **~16 200** |

Plus dedicated scrapers for Apple, Amazon, Google, Meta, Microsoft, Nvidia,
Tesla, TikTok, Uber, Bloomberg, YC, and more.

## Install

```bash
pip install jobhive
```

Optional extras:

```bash
pip install "jobhive[parquet]"     # faster downloads via Apache Parquet
pip install "jobhive[scrapers]"    # build your own pipeline
pip install "jobhive[publish]"     # push your own dataset to Cloudflare R2
pip install "jobhive[all]"         # everything
```

## Three layers of API

### 1. Dataset client — query the public snapshot

```python
from jobhive import search

# Free-text title + location + remote filter
df = search(query="rust", location="Berlin", remote=True, salary_min=80_000)

# Restrict to a single ATS slice (smaller download)
df = search(query="data engineer", ats="ashby")

# Pandas all the way down
df.groupby("company").size().sort_values(ascending=False).head(20)
```

### 2. Per-ATS scrapers — bring your own companies

```python
from jobhive.scrapers import GreenhouseScraper, LeverScraper, AshbyScraper

jobs = GreenhouseScraper("openai").fetch()       # → list[Job]
jobs = LeverScraper("anthropic").fetch()
jobs = AshbyScraper("ramp").fetch()
```

Or pick by name:

```python
from jobhive.scrapers import get_scraper
scraper = get_scraper("greenhouse", "openai")
```

#### Scraper status

**Multi-tenant ATS — stable**, live-validated against production sites:

| ATS | Class | Slug shape |
|---|---|---|
| Greenhouse | `GreenhouseScraper` | board slug (`openai`) |
| Lever | `LeverScraper` | account slug (`anthropic`) |
| Ashby | `AshbyScraper` | board slug (`ramp`) — surfaces structured salary when Pay Transparency is on |
| SmartRecruiters | `SmartRecruitersScraper` | company slug (`Filmless`) |
| Workable | `WorkableScraper` | account slug (`1000heads`) |
| Rippling | `RipplingScraper` | board slug (`11fs-group-ltd`) |
| Personio | `PersonioScraper` | tenant subdomain (`1komma5grad`) or full URL |
| Gem | `GemScraper` | board slug (`accel`, `11x-ai`) |
| Join.com | `JoinComScraper` | company slug (`6pmseason`) |

**Big-tech custom — stable**, live-validated, single-tenant per scraper:

| Company | Class | Slug |
|---|---|---|
| Amazon | `AmazonScraper` | (any — global API) |
| Apple | `AppleScraper` | (any — global API, CSRF flow) |
| Microsoft | `MicrosoftScraper` | (any — Eightfold PCSX) |
| Nvidia | `NvidiaScraper` | (any — Eightfold PCSX) |
| TikTok | `TikTokScraper` | (any — lifeattiktok.com) |
| Uber | `UberScraper` | (any — uber.com/api) |

**Hybrid jobboards — stable**, companies post directly (not aggregated):

| Provider | Class | Slug | Notes |
|---|---|---|---|
| Welcome to the Jungle | `WTTJScraper` | org slug or `"*"` | Algolia-backed; ~81k active jobs globally with rich structured data (salary, contract type, lat/lon, description, sectors). Pass `"*"` to walk the entire platform (~56s). |

⚠️  **Experimental** — these ship a working URL pattern but require
per-tenant tweaks for reliable extraction across all customers. They
work for some tenants out of the box; for others, fall back to the
upstream [stapply-ai/data](https://github.com/stapply-ai/data) legacy
scrapers until 0.2.0:

| Provider | Class | Why it's experimental |
|---|---|---|
| Workday | `WorkdayScraper` | Site path varies; some tenants need extra `appliedFacets` |
| Oracle HCM | `OracleScraper` | Field names (`Title` vs `RequisitionTitle`) differ across versions |
| Phenom | `PhenomScraper` | Each tenant configures its own API prefix |
| Avature | `AvatureScraper` | Server-rendered HTML, markup varies per template |
| Mercor | `MercorScraper` | Listing migrated to client-side rendering |
| Google | `GoogleScraper` | HTML-only, markup changes periodically |

**Browser-required** — these endpoints are gated by Akamai / require
session tokens that only a real browser can issue. The scrapers raise a
clear `ScraperError` directing users to the legacy Playwright-based
implementations until jobhive 0.2 ships an optional browser backend:

| Company | Class | Why a browser is needed |
|---|---|---|
| Tesla | `TeslaScraper` | Akamai bot detection blocks direct httpx calls |
| Meta | `MetaScraper` | Site is CSR, GraphQL needs browser-issued tokens |

### 3. Full pipeline — discover, scrape, enrich, publish

```python
from jobhive import Pipeline   # coming in 0.2

Pipeline() \
    .discover(ats="lever", queries=20) \
    .scrape() \
    .enrich() \
    .to_csv("jobs.csv")
```

## CLI

```bash
jobhive search "platform engineer" --location Paris --limit 20
jobhive scrape greenhouse openai
jobhive list-ats
jobhive publish ./data --pattern '{ats}/jobs.csv'
```

## How the data flows

```
┌─────────────────┐    ┌──────────────────┐    ┌───────────────┐
│   Discovery     │───▶│   ATS Scrapers   │───▶│   Enrichment   │
│ SearXNG/Serp/   │    │  Greenhouse,     │    │  Salary parse  │
│ Firecrawl       │    │  Lever, Ashby... │    │  Geocoding     │
└─────────────────┘    └──────────────────┘    └───────┬───────┘
                                                       │
                                                       ▼
                                          ┌────────────────────────┐
                                          │  Cloudflare R2         │
                                          │  storage.stapply.ai/   │
                                          │  jobhive/v1/           │
                                          └────────────────────────┘
                                                       │
                                                       ▼
                                          ┌────────────────────────┐
                                          │  jobhive Python client │
                                          └────────────────────────┘
```

## Add a new ATS scraper

The scraper API is small on purpose: subclass `BaseScraper`, set `ats`, and
implement `fetch()`.

```python
from jobhive.scrapers.base import BaseScraper, ScraperRegistry
from jobhive.models import ATSType, Job

@ScraperRegistry.register(ATSType.CUSTOM)
class MyAtsScraper(BaseScraper):
    ats = ATSType.CUSTOM

    def fetch(self) -> list[Job]:
        ...  # return [Job(...), Job(...)]
```

**The fast way** — point
[reverse-api-engineer](https://github.com/kalil0321/reverse-api-engineer) at
the ATS's careers page. It records the browser's network traffic to a HAR
file and generates a typed Python client. Drop the generated client into
`jobhive/scrapers/`, wire it into `BaseScraper.fetch()`, and you're done.
Every scraper in this repo was built that way.

## Dataset layout on R2

Everything lives under `https://storage.stapply.ai/jobhive/v1/`:

```
jobhive/v1/
├── manifest.json                    # always start here
├── jobs/
│   ├── all.parquet                  # full snapshot — parquet ONLY (~40 MB)
│   ├── by-ats/
│   │   ├── greenhouse.parquet       # one file per ATS
│   │   ├── greenhouse.csv           # CSV alongside (smaller files)
│   │   └── ...
│   └── by-date/
│       └── 2026-05-04.parquet       # daily snapshot, immutable
└── companies/
    ├── all.csv                      # global slug → ATS mapping
    └── by-ats/
        ├── greenhouse.csv           # companies on Greenhouse
        ├── lever.csv                # companies on Lever
        └── ...
```

**Schema** — every job row carries:

```
url, title, company, ats_type, ats_id,
location, lat, lon, is_remote,
salary_currency, salary_period, salary_summary, salary_min, salary_max,
experience, employment_type, seniority, department, team,
posted_at, fetched_at, description
```

Optional fields are `None` when the source ATS doesn't expose them. `is_remote`
and `seniority` are derived (location keywords; title regex). Manifest
fields are stable across the v1 series; new fields may be added but existing
ones never change meaning.

### Visualizing parquet locally

```bash
# DuckDB CLI — fastest, supports SQL
duckdb -c "SELECT title, company, salary_summary FROM 'jobs.parquet' LIMIT 10"

# Pandas
python -c "import pandas as pd; print(pd.read_parquet('jobs.parquet').head())"

# Tad (Mac/Linux GUI)
brew install --cask tad

# VS Code: install "Parquet Viewer" extension and drag the file in
```

## Run your own publisher

If you've cloned [stapply-ai/data](https://github.com/stapply-ai/data) and
want to push the local snapshot to your own R2 bucket:

```bash
# Required
export CLOUDFLARE_BUCKET_NAME=...
export CLOUDFLARE_ACCESS_KEY_ID=...
export CLOUDFLARE_SECRET_ACCESS_KEY=...

# Either of these — endpoint wins if both are set
export CLOUDFLARE_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
# or
export CLOUDFLARE_ACCOUNT_ID=<your-account-id>

# Optional — public CDN base for nice URLs in the manifest
export CLOUDFLARE_PUBLIC_BASE_URL=https://your-cdn.example.com

uv run python jobhive/scripts/publish_to_cloudflare.py
```

The script ships ~150 MB of CSV + Parquet to R2 in a few minutes and writes a
fresh `manifest.json` last so half-finished runs never poison clients.

## Project layout

```
jobhive/
├── src/jobhive/
│   ├── client.py            # Layer 1: dataset client
│   ├── manifest.py          # versioned R2 manifest
│   ├── models.py            # Job / Company / Salary
│   ├── scrapers/            # Layer 2: per-ATS scrapers
│   ├── pipeline/            # Layer 3: end-to-end orchestration
│   ├── discovery/           # find new companies on each ATS
│   ├── enrichment/          # salary, geocoding, classification
│   ├── storage/             # Cloudflare R2 + dataset publisher
│   └── cli.py
├── tests/
├── scripts/                 # publish_to_cloudflare.py, etc.
└── examples/
```

## Tests

```bash
cd jobhive
uv pip install -e ".[dev,publish,scrapers]"
pytest          # 162 tests, no network
ruff check .
```

## License

MIT.

## Related

- **[reverse-api-engineer](https://github.com/kalil0321/reverse-api-engineer)** —
  the tool we used to build every scraper here. Captures browser traffic
  and generates a typed Python API client; that's what makes adding a new
  ATS a 30-minute job.
- **[stapply-ai/data](https://github.com/stapply-ai/data)** — the upstream
  scrapers and discovery pipeline.
- **[stapply.ai map](https://map.stapply.ai)** — interactive visualization
  of the jobhive dataset.
