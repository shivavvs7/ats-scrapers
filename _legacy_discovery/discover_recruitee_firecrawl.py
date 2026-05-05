#!/usr/bin/env python3
"""Bulk-discover Recruitee tenants via Firecrawl search.

Generates diverse search queries (industries, countries, generic keywords),
sends each to Firecrawl's `/v1/search` endpoint, aggregates `*.recruitee.com`
URLs, validates each via the public `/api/offers` endpoint, and writes the
results to `recruitee/recruitee_companies.csv`.

Reads `FIRECRAWL_API_KEY` from environment (or from `<repo>/.env`).

Usage:
    uv run python jobhive/scripts/discover_recruitee_firecrawl.py [--max-queries 50]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import sys
from datetime import datetime
from itertools import product
from pathlib import Path

import httpx

SLUG_RE = re.compile(
    r"https?://(?P<slug>[a-z0-9][a-z0-9-]{0,62})\.recruitee\.com",
    re.IGNORECASE,
)
SKIP_SLUGS = {
    "www", "api", "support", "help", "tellent", "blog", "status",
    "developers", "partners", "jobs", "recruitee", "recruitee3",
}

# Diverse query bank — combines industries × countries × keywords for breadth.
INDUSTRIES = [
    "tech", "fintech", "saas", "ecommerce", "logistics", "retail",
    "healthcare", "biotech", "manufacturing", "education", "marketing",
    "consulting", "agency", "media", "construction", "automotive",
    "energy", "renewable", "real estate", "hospitality", "transport",
    "food", "fashion", "gaming", "cybersecurity", "aerospace",
]
COUNTRIES = [
    "Netherlands", "Germany", "France", "Belgium", "Spain", "Italy",
    "Sweden", "Norway", "Finland", "Denmark", "Poland", "Austria",
    "Portugal", "Switzerland", "Ireland", "United Kingdom", "Czech Republic",
    "Romania", "Hungary", "Greece", "Canada", "Australia",
]
KEYWORDS = [
    "careers", "jobs", "hiring", "open positions", "apply", "vacancies",
    "we are hiring", "join our team", "recruitment",
]

PROVIDER_HINT = "recruitee.com"


def build_queries(max_queries: int) -> list[str]:
    queries: list[str] = []
    # Cross product industry × keyword
    for ind, kw in product(INDUSTRIES, KEYWORDS[:5]):
        queries.append(f"{PROVIDER_HINT} {kw} {ind}")
    # Country × keyword
    for country, kw in product(COUNTRIES, KEYWORDS[:5]):
        queries.append(f"{PROVIDER_HINT} {kw} {country}")
    # Direct subdomain hunt
    queries.extend(
        [
            f"site:{PROVIDER_HINT} jobs",
            f"site:{PROVIDER_HINT} careers",
            f"site:{PROVIDER_HINT} open positions",
            f"site:{PROVIDER_HINT} hiring",
            f'"powered by recruitee"',
            f'"hiring on recruitee"',
            f"recruitee careers homepage",
        ]
    )
    # Dedupe + cap
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out[:max_queries]


async def firecrawl_search(
    client: httpx.AsyncClient, api_key: str, query: str, *, limit: int = 50
) -> list[str]:
    """Return list of URLs from Firecrawl /v1/search."""
    try:
        r = await client.post(
            "https://api.firecrawl.dev/v1/search",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"query": query, "limit": limit},
            timeout=30,
        )
    except httpx.HTTPError:
        return []
    if r.status_code != 200:
        return []
    try:
        payload = r.json()
    except ValueError:
        return []
    items = payload.get("data") or []
    if not isinstance(items, list):
        return []
    urls: list[str] = []
    for item in items:
        if isinstance(item, dict):
            for key in ("url", "link"):
                value = item.get(key)
                if isinstance(value, str):
                    urls.append(value)
                    break
    return urls


async def validate(client: httpx.AsyncClient, slug: str) -> tuple[str, int] | None:
    url = f"https://{slug}.recruitee.com/api/offers"
    try:
        r = await client.get(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=15,
        )
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    offers = data.get("offers") or []
    if not isinstance(offers, list):
        return None
    company = None
    for o in offers:
        if isinstance(o, dict) and o.get("company_name"):
            company = o["company_name"]
            break
    return (company or slug, len(offers))


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def run(api_key: str, queries: list[str], existing: set[str], concurrency: int) -> dict[str, tuple[str, int]]:
    found_slugs: set[str] = set()
    started = datetime.now()

    async with httpx.AsyncClient(follow_redirects=True) as client:
        sem = asyncio.Semaphore(concurrency)

        async def query_task(q: str) -> None:
            async with sem:
                urls = await firecrawl_search(client, api_key, q)
            for u in urls:
                m = SLUG_RE.search(u)
                if m:
                    slug = m.group("slug").lower()
                    if slug not in SKIP_SLUGS:
                        found_slugs.add(slug)

        await asyncio.gather(*(query_task(q) for q in queries))

        candidates = sorted(found_slugs - existing)
        print(
            f"  searches done in {(datetime.now()-started).total_seconds():.0f}s — "
            f"{len(found_slugs)} unique slugs ({len(candidates)} new vs existing)"
        )

        valid: dict[str, tuple[str, int]] = {}
        sem2 = asyncio.Semaphore(concurrency)

        async def validate_task(slug: str) -> None:
            async with sem2:
                result = await validate(client, slug)
            if result is not None:
                valid[slug] = result

        await asyncio.gather(*(validate_task(s) for s in candidates))
    return valid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "recruitee" / "recruitee_companies.csv",
    )
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--max-queries", type=int, default=80)
    parser.add_argument(
        "--no-dotenv",
        action="store_true",
        help="Don't auto-load FIRECRAWL_API_KEY from <repo>/.env",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    if not args.no_dotenv:
        load_dotenv(repo_root / ".env")

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        print("FIRECRAWL_API_KEY not set", file=sys.stderr)
        return 1

    # Existing CSV — we merge new finds into it instead of overwriting blindly
    existing: dict[str, str] = {}  # slug -> name
    if args.output.exists():
        with args.output.open() as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) < 2:
                    continue
                m = SLUG_RE.search(row[1])
                if m:
                    existing[m.group("slug").lower()] = row[0]

    queries = build_queries(args.max_queries)
    print(f"Running {len(queries)} Firecrawl searches with concurrency={args.concurrency}...")
    print(f"Existing CSV has {len(existing)} tenants — searching for additions only.")
    valid = asyncio.run(run(api_key, queries, set(existing.keys()), args.concurrency))

    # Merge: keep existing, add new
    merged: dict[str, str] = dict(existing)
    job_counts: dict[str, int] = {}
    new_count = 0
    for slug, (name, total) in valid.items():
        if slug not in merged:
            new_count += 1
        merged[slug] = name
        job_counts[slug] = total

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "url"])
        for slug, name in sorted(merged.items()):
            writer.writerow([name, f"https://{slug}.recruitee.com"])

    print(f"\nWrote: {args.output}")
    print(f"Total tenants in CSV:  {len(merged)}")
    print(f"  newly added:         {new_count}")
    print(f"  already known:       {len(merged) - new_count}")
    print(f"New jobs unlocked:     {sum(t for s, t in job_counts.items() if s not in existing):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
