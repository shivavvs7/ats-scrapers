#!/usr/bin/env python3
"""Discover Recruitee tenants by mining exa search outputs + validating each
via the public `/api/offers` endpoint.

Inputs:
    - One or more text/JSON files (typically the tool-results dumps from
      Exa searches over `recruitee.com`).

Output:
    - `recruitee/recruitee_companies.csv` with columns name,url,total_jobs

The validator hits `https://{slug}.recruitee.com/api/offers` once per
candidate slug and keeps only those that respond 200 with at least one
parseable offer.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import httpx

SLUG_RE = re.compile(
    r"https?://(?P<slug>[a-z0-9][a-z0-9-]{0,62})\.recruitee\.com",
    re.IGNORECASE,
)
# Reserved subdomains that aren't real tenants
SKIP = {
    "www", "api", "support", "help", "tellent", "blog",
    "status", "developers", "partners", "jobs",
}


async def validate(client: httpx.AsyncClient, slug: str) -> tuple[str, int] | None:
    """Return (display_name, job_count) if slug is a valid Recruitee tenant."""
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
    company_name = None
    for o in offers:
        if isinstance(o, dict) and o.get("company_name"):
            company_name = o["company_name"]
            break
    return (company_name or slug, len(offers))


async def run(slugs: list[str], concurrency: int) -> list[dict[str, object]]:
    sem = asyncio.Semaphore(concurrency)
    results: list[dict[str, object]] = []
    started = datetime.now()

    async with httpx.AsyncClient(follow_redirects=True) as client:

        async def task(slug: str) -> None:
            async with sem:
                discovered = await validate(client, slug)
            if discovered is not None:
                name, total = discovered
                results.append(
                    {
                        "name": name,
                        "slug": slug,
                        "url": f"https://{slug}.recruitee.com",
                        "total_jobs": total,
                    }
                )
            done_count = len([s for s in slugs if s not in pending])
            pending.discard(slug)
            n = len(slugs) - len(pending)
            if n % 50 == 0:
                elapsed = (datetime.now() - started).total_seconds()
                print(
                    f"  {n}/{len(slugs)}  valid={len(results)}  elapsed={elapsed:.0f}s",
                    flush=True,
                )

        pending = set(slugs)
        await asyncio.gather(*(task(s) for s in slugs))
    return results


def extract_slugs(paths: list[Path]) -> set[str]:
    slugs: set[str] = set()
    for path in paths:
        text = path.read_text(errors="ignore")
        for match in SLUG_RE.finditer(text):
            slug = match.group("slug").lower()
            if slug and slug not in SKIP:
                slugs.add(slug)
    return slugs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs",
        type=Path,
        nargs="+",
        help="One or more text/JSON files containing Recruitee URLs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "recruitee" / "recruitee_companies.csv",
    )
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()

    slugs = sorted(extract_slugs(args.inputs))
    if not slugs:
        print("No Recruitee slugs found in inputs.", file=sys.stderr)
        return 1
    print(f"Found {len(slugs)} candidate slugs. Validating with concurrency={args.concurrency}...")

    results = asyncio.run(run(slugs, args.concurrency))
    results.sort(key=lambda r: -int(r["total_jobs"]))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "url"])
        for r in results:
            writer.writerow([r["name"], r["url"]])

    print(f"\nWrote: {args.output}")
    print(f"Valid Recruitee tenants:   {len(results)}")
    print(f"Total jobs across tenants: {sum(int(r['total_jobs']) for r in results):,}")
    print("\nTop 10 by job count:")
    for r in results[:10]:
        print(f"  {int(r['total_jobs']):>5}  {r['name']:30s} {r['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
