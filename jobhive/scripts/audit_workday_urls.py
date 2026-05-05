#!/usr/bin/env python3
"""Audit a Workday companies CSV: probe each URL and flag the dead ones.

Reads `<repo>/workday/workday_companies.csv` (columns: name,url),
makes a single POST against each tenant's `/wday/cxs/.../jobs` endpoint,
and writes `workday_audit_<timestamp>.csv` with these columns:

    name, url, status, total_jobs, error

Run:
    uv run python jobhive/scripts/audit_workday_urls.py [--limit 100]

This is read-only against R2 — only HTTP probes against the Workday tenants.
Concurrent (default 25 in flight) so 2,800 URLs probe in 3-5 minutes.
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

URL_PATTERN = re.compile(
    r"^https://(?P<company>[^.]+)\.(?P<instance>wd\d+)\.myworkdayjobs\.com/(?P<site>[^/?#]+)"
)


async def probe(client: httpx.AsyncClient, name: str, url: str) -> dict[str, object]:
    out: dict[str, object] = {
        "name": name,
        "url": url,
        "status": "",
        "total_jobs": "",
        "error": "",
    }
    match = URL_PATTERN.match(url.rstrip("/"))
    if not match:
        out["status"] = "BAD_URL"
        out["error"] = "URL does not match Workday pattern"
        return out
    company = match.group("company")
    instance = match.group("instance")
    site = match.group("site")
    api = f"https://{company}.{instance}.myworkdayjobs.com/wday/cxs/{company}/{site}/jobs"

    try:
        response = await client.post(
            api,
            json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        out["status"] = "NETWORK_ERROR"
        out["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        return out

    out["status"] = str(response.status_code)
    if response.status_code == 200:
        try:
            data = response.json()
            out["total_jobs"] = data.get("total", 0)
        except ValueError:
            out["error"] = "non-JSON response"
    elif response.status_code == 404:
        out["error"] = "site not found"
    elif response.status_code >= 500:
        out["error"] = response.text[:120]
    else:
        out["error"] = f"unexpected {response.status_code}: {response.text[:120]}"
    return out


async def run(rows: list[dict[str, str]], concurrency: int) -> list[dict[str, object]]:
    sem = asyncio.Semaphore(concurrency)
    results: list[dict[str, object]] = []
    started = datetime.now()

    async with httpx.AsyncClient(follow_redirects=True) as client:

        async def task(row: dict[str, str]) -> None:
            async with sem:
                r = await probe(client, row.get("name", ""), row.get("url", ""))
            results.append(r)
            done = len(results)
            if done % 50 == 0:
                elapsed = (datetime.now() - started).total_seconds()
                pct = done * 100 // len(rows)
                ok = sum(1 for x in results if x["status"] == "200")
                print(
                    f"  {done}/{len(rows)} ({pct}%)  ok={ok}  elapsed={elapsed:.0f}s",
                    flush=True,
                )

        await asyncio.gather(*(task(r) for r in rows))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "workday" / "workday_companies.csv",
        help="Input CSV (default: workday/workday_companies.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV (default: workday_audit_<timestamp>.csv)",
    )
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--limit", type=int, default=None, help="Probe only N rows (for testing)")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    rows = list(csv.DictReader(args.input.open()))
    if args.limit:
        rows = rows[: args.limit]
    print(f"Probing {len(rows)} Workday URLs with concurrency={args.concurrency}...")

    results = asyncio.run(run(rows, args.concurrency))

    output = args.output or Path.cwd() / f"workday_audit_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "url", "status", "total_jobs", "error"])
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    # Summary
    by_status: dict[str, int] = {}
    total_jobs = 0
    for r in results:
        s = str(r["status"])
        by_status[s] = by_status.get(s, 0) + 1
        try:
            total_jobs += int(r["total_jobs"] or 0)
        except (TypeError, ValueError):
            pass
    print(f"\nWrote: {output}")
    print(f"Total rows: {len(results)}")
    for status, count in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"  {status:>14s}: {count}")
    print(f"Total jobs across healthy URLs: {total_jobs:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
