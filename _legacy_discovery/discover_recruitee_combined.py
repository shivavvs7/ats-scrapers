#!/usr/bin/env python3
"""Combined Recruitee tenant discovery: SerpAPI (Google) + Firecrawl /map.

Why combined:
  * SerpAPI hits Google directly with `site:recruitee.com` queries — surfaces
    long-tail tenants Firecrawl /search misses.
  * Firecrawl /map on recruitee.com / tellent.com surfaces marketing-page
    references and customer logos that aren't easily search-indexed.

Validation: every candidate slug is hit at `https://{slug}.recruitee.com/api/offers`.
Only tenants returning HTTP 200 with parseable JSON are kept.

The script merges into `recruitee/recruitee_companies.csv` (additive — never
removes existing entries).
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
    "support2", "demo",
}

# ---- query banks ----

INDUSTRIES = [
    "tech", "fintech", "saas", "ecommerce", "logistics", "retail",
    "healthcare", "biotech", "manufacturing", "education", "marketing",
    "consulting", "agency", "media", "construction", "automotive",
    "energy", "renewable", "real estate", "hospitality", "transport",
    "food", "fashion", "gaming", "cybersecurity", "aerospace",
    "ai", "ml", "robotics", "agritech", "edtech", "proptech",
    "crypto", "telco", "insurance", "pharma", "legal",
]
COUNTRIES = [
    "Netherlands", "Germany", "France", "Belgium", "Spain", "Italy",
    "Sweden", "Norway", "Finland", "Denmark", "Poland", "Austria",
    "Portugal", "Switzerland", "Ireland", "United Kingdom", "Czech Republic",
    "Romania", "Hungary", "Greece", "Canada", "Australia",
    "Estonia", "Lithuania", "Latvia", "Slovakia", "Slovenia",
    "Bulgaria", "Croatia", "Luxembourg", "Singapore", "Israel",
]
KEYWORDS = ["careers", "jobs", "hiring", "apply", "open positions"]

PROVIDER = "recruitee.com"


def build_serp_queries() -> list[str]:
    """SerpAPI loves precise `site:` queries."""
    queries = [
        f"site:{PROVIDER} -inurl:www -inurl:tellent -inurl:jobs",
        f"site:{PROVIDER} careers",
        f"site:{PROVIDER} apply",
        f"site:{PROVIDER} hiring",
        f"site:{PROVIDER} open positions",
        f'"powered by recruitee"',
        f'"hiring on recruitee"',
        f'"recruitee" intitle:careers',
    ]
    # Plus narrowed `site:` queries by keyword in URL
    queries.extend(
        f"site:{PROVIDER} inurl:o {kw}" for kw in ["engineer", "manager", "developer", "designer", "sales"]
    )
    return queries


def build_firecrawl_queries() -> list[str]:
    queries: list[str] = []
    for ind, kw in product(INDUSTRIES, KEYWORDS[:3]):
        queries.append(f"{PROVIDER} {kw} {ind}")
    for country, kw in product(COUNTRIES, KEYWORDS[:2]):
        queries.append(f"{PROVIDER} {kw} {country}")
    return queries


# ---- search backends ----

async def serpapi_search(
    client: httpx.AsyncClient, key: str, query: str, *, num: int = 100
) -> list[str]:
    try:
        r = await client.get(
            "https://serpapi.com/search.json",
            params={"q": query, "engine": "google", "num": num, "api_key": key},
            timeout=30,
        )
    except httpx.HTTPError:
        return []
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except ValueError:
        return []
    urls: list[str] = []
    for result in data.get("organic_results") or []:
        if isinstance(result, dict) and isinstance(result.get("link"), str):
            urls.append(result["link"])
    return urls


async def firecrawl_search(
    client: httpx.AsyncClient, key: str, query: str, *, limit: int = 50
) -> list[str]:
    try:
        r = await client.post(
            "https://api.firecrawl.dev/v1/search",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"query": query, "limit": limit},
            timeout=30,
        )
    except httpx.HTTPError:
        return []
    if r.status_code != 200:
        return []
    try:
        items = r.json().get("data") or []
    except ValueError:
        return []
    out: list[str] = []
    for item in items:
        if isinstance(item, dict):
            for k in ("url", "link"):
                v = item.get(k)
                if isinstance(v, str):
                    out.append(v)
                    break
    return out


async def firecrawl_map(client: httpx.AsyncClient, key: str, url: str) -> list[str]:
    """Use Firecrawl /map to extract all linked URLs from a domain."""
    try:
        r = await client.post(
            "https://api.firecrawl.dev/v1/map",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"url": url, "limit": 5000},
            timeout=60,
        )
    except httpx.HTTPError:
        return []
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except ValueError:
        return []
    links = data.get("links") or data.get("data") or []
    if isinstance(links, list):
        return [link for link in links if isinstance(link, str)]
    return []


# ---- validate ----

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
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def extract_slugs(urls: list[str]) -> set[str]:
    out: set[str] = set()
    for url in urls:
        m = SLUG_RE.search(url)
        if not m:
            continue
        slug = m.group("slug").lower()
        if slug and slug not in SKIP_SLUGS:
            out.add(slug)
    return out


async def run(
    serp_key: str | None,
    fc_key: str | None,
    existing_slugs: set[str],
    concurrency: int,
) -> dict[str, tuple[str, int]]:
    started = datetime.now()
    found_slugs: set[str] = set()

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # 1. SerpAPI (sequential — SerpAPI rate-limits aggressive parallelism)
        if serp_key:
            for query in build_serp_queries():
                urls = await serpapi_search(client, serp_key, query)
                slugs = extract_slugs(urls)
                new = slugs - found_slugs - existing_slugs
                if new:
                    print(f"  [serp] {query[:60]:60s}  +{len(new)} new")
                found_slugs.update(slugs)

        # 2. Firecrawl /map on Recruitee + Tellent marketing
        if fc_key:
            for url in [
                "https://recruitee.com",
                "https://tellent.com",
                "https://jobs.recruitee.com",
            ]:
                urls = await firecrawl_map(client, fc_key, url)
                slugs = extract_slugs(urls)
                new = slugs - found_slugs - existing_slugs
                print(f"  [map ] {url:35s}  links={len(urls)}  +{len(new)} new")
                found_slugs.update(slugs)

        # 3. Firecrawl /search (parallel)
        if fc_key:
            sem = asyncio.Semaphore(concurrency)

            async def fc_task(q: str) -> list[str]:
                async with sem:
                    return await firecrawl_search(client, fc_key, q)

            queries = build_firecrawl_queries()
            print(f"  [fc  ] running {len(queries)} parallel /search calls...")
            url_lists = await asyncio.gather(*(fc_task(q) for q in queries))
            for urls in url_lists:
                found_slugs.update(extract_slugs(urls))

        candidates = sorted(found_slugs - existing_slugs)
        elapsed = (datetime.now() - started).total_seconds()
        print(f"\nDiscovery done in {elapsed:.0f}s — total unique slugs={len(found_slugs)}, new candidates={len(candidates)}")

        # 4. Validate
        valid: dict[str, tuple[str, int]] = {}
        sem2 = asyncio.Semaphore(concurrency)

        async def vt(slug: str) -> None:
            async with sem2:
                r = await validate(client, slug)
            if r is not None:
                valid[slug] = r

        await asyncio.gather(*(vt(s) for s in candidates))
    return valid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "recruitee" / "recruitee_companies.csv",
    )
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    load_dotenv(repo / ".env")

    serp_key = os.getenv("SERPAPI_API_KEY")
    fc_key = os.getenv("FIRECRAWL_API_KEY")
    if not serp_key and not fc_key:
        print("Need SERPAPI_API_KEY or FIRECRAWL_API_KEY", file=sys.stderr)
        return 1

    existing: dict[str, str] = {}
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
    print(f"Existing CSV has {len(existing)} tenants.")

    valid = asyncio.run(run(serp_key, fc_key, set(existing.keys()), args.concurrency))

    merged = dict(existing)
    new_count = 0
    for slug, (name, _total) in valid.items():
        if slug not in merged:
            new_count += 1
        merged[slug] = name

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "url"])
        for slug, name in sorted(merged.items()):
            writer.writerow([name, f"https://{slug}.recruitee.com"])

    print(f"\nWrote: {args.output}")
    print(f"Total tenants:  {len(merged)}  (was {len(existing)}, +{new_count} new)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
