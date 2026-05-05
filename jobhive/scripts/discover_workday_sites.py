#!/usr/bin/env python3
"""Re-discover the real `site` path for Workday tenants whose recorded URLs
are all dead.

For each tenant `{company}.wd{N}.myworkdayjobs.com`, we:
  1. GET the host root (`https://{co}.wd{N}.myworkdayjobs.com/`) — Workday
     usually redirects to the canonical careers site path.
  2. If that's not enough, scan the response HTML for any reference to
     `myworkdayjobs.com/<site>` and probe each candidate against the
     `wday/cxs/.../jobs` API.
  3. Output a CSV with the discovered URL + its job count.

Usage:
    uv run python jobhive/scripts/discover_workday_sites.py \
        --audit /path/to/workday_audit_TIMESTAMP.csv

Reads only the rows whose status != 200 to figure out which tenants need
rediscovery. Writes `workday_discovery_<ts>.csv` with name,url,total_jobs.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

URL_PATTERN = re.compile(
    r"^https://(?P<company>[^.]+)\.(?P<instance>wd\d+)\.myworkdayjobs\.com"
)
SITE_PATH_RE = re.compile(
    r"myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?(?P<site>[A-Za-z0-9_-]{2,80})"
)


async def probe_site(
    client: httpx.AsyncClient, company: str, instance: str, site: str
) -> int | None:
    """Return total job count for {company}/{instance}/{site}, or None."""
    api = (
        f"https://{company}.{instance}.myworkdayjobs.com/wday/cxs/"
        f"{company}/{site}/jobs"
    )
    try:
        r = await client.post(
            api,
            json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        return int(r.json().get("total", 0))
    except (ValueError, KeyError):
        return None


async def discover_tenant(
    client: httpx.AsyncClient, company: str, instance: str
) -> tuple[str, int] | None:
    """Find a working site path for `{company}.{instance}.myworkdayjobs.com`.

    Returns (full_url, total_jobs) on success, None otherwise.
    """
    host = f"https://{company}.{instance}.myworkdayjobs.com"

    # Step 1: GET root, Workday usually 302s to the canonical site
    try:
        r = await client.get(host, timeout=15, follow_redirects=True)
    except httpx.HTTPError:
        return None

    # If redirected, the final URL may already include the site
    final = str(r.url)
    match = re.search(rf"^https://{re.escape(company)}\.{instance}\.myworkdayjobs\.com/(?:[a-z]{{2}}-[A-Z]{{2}}/)?(?P<site>[A-Za-z0-9_-]{{2,80}})", final)
    candidates: list[str] = []
    if match:
        candidates.append(match.group("site"))

    # Step 2: scan HTML for any /myworkdayjobs.com/<site>/ patterns
    for m in SITE_PATH_RE.finditer(r.text):
        site = m.group("site")
        # Filter out obvious noise
        if site in {"jobs", "wday", "static", "assets", "common"}:
            continue
        if site not in candidates:
            candidates.append(site)
        if len(candidates) >= 8:
            break

    # Step 3: probe each candidate
    for site in candidates:
        total = await probe_site(client, company, instance, site)
        if total is not None and total > 0:
            return (f"{host}/{site}", total)
    # Fallback: try a couple of common defaults
    for default in ("External", "external", "Search", "search"):
        if default in candidates:
            continue
        total = await probe_site(client, company, instance, default)
        if total is not None and total > 0:
            return (f"{host}/{default}", total)
    return None


async def run(tenants: list[tuple[str, str, str]], concurrency: int) -> list[dict[str, object]]:
    sem = asyncio.Semaphore(concurrency)
    results: list[dict[str, object]] = []
    started = datetime.now()

    async with httpx.AsyncClient(follow_redirects=True) as client:

        async def task(name: str, company: str, instance: str) -> None:
            async with sem:
                discovered = await discover_tenant(client, company, instance)
            if discovered is None:
                results.append(
                    {"name": name, "url": "", "total_jobs": 0, "status": "no_site_found"}
                )
            else:
                url, total = discovered
                results.append(
                    {"name": name, "url": url, "total_jobs": total, "status": "found"}
                )
            done = len(results)
            if done % 20 == 0:
                elapsed = (datetime.now() - started).total_seconds()
                ok = sum(1 for x in results if x["status"] == "found")
                print(
                    f"  {done}/{len(tenants)}  found={ok}  elapsed={elapsed:.0f}s",
                    flush=True,
                )

        await asyncio.gather(*(task(n, c, i) for n, c, i in tenants))
    return results


def parse_tenants_from_audit(audit_csv: Path) -> list[tuple[str, str, str]]:
    """Return (name, company, instance) tuples for companies whose every URL
    in the audit had status != 200."""
    by_company: dict[str, list[str]] = defaultdict(list)
    by_company_meta: dict[str, tuple[str, str]] = {}
    with audit_csv.open() as f:
        for row in csv.DictReader(f):
            name = row["name"]
            url = row["url"]
            by_company[name].append(row["status"])
            match = URL_PATTERN.match(url.rstrip("/"))
            if match and name not in by_company_meta:
                by_company_meta[name] = (match.group("company"), match.group("instance"))
    out = []
    for name, statuses in by_company.items():
        if "200" in statuses:
            continue
        meta = by_company_meta.get(name)
        if meta is None:
            continue
        company, instance = meta
        out.append((name, company, instance))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit",
        type=Path,
        required=True,
        help="Path to the audit CSV produced by audit_workday_urls.py",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV (default: workday_discovery_<timestamp>.csv)",
    )
    parser.add_argument("--concurrency", type=int, default=15)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if not args.audit.exists():
        print(f"Audit CSV not found: {args.audit}", file=sys.stderr)
        return 1

    tenants = parse_tenants_from_audit(args.audit)
    if args.limit:
        tenants = tenants[: args.limit]
    print(f"Rediscovering {len(tenants)} dead tenants with concurrency={args.concurrency}...")

    results = asyncio.run(run(tenants, args.concurrency))

    output = args.output or Path.cwd() / f"workday_discovery_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "url", "total_jobs", "status"])
        writer.writeheader()
        writer.writerows(results)

    found = [r for r in results if r["status"] == "found"]
    total_jobs = sum(int(r["total_jobs"] or 0) for r in found)
    print(f"\nWrote: {output}")
    print(f"Tenants probed:    {len(results)}")
    print(f"Sites recovered:   {len(found)} ({len(found)*100//max(len(results),1)}%)")
    print(f"New jobs unlocked: {total_jobs:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
