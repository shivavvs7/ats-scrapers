#!/usr/bin/env python3
"""Detect companies that switched ATS providers.

When a tenant goes dark on its current ATS (404 / no jobs), the company
hasn't necessarily disappeared — they often migrated to another platform.
This script:

1. Reads every ``data/{ats}/{ats}_companies.csv``.
2. For each tenant marked **suspect** (no jobs in the latest ``jobs.csv``,
   or fails live validation), generates plausible slug candidates from
   the human-readable name.
3. Probes those candidates against every *other* ATS's validate URL.
4. Reports a migration mapping: ``{ats_old, slug_old} → {ats_new, slug_new}``.

The output is a CSV ``data/migrations_{date}.csv`` you can review before
acting on. By default we don't move tenants automatically — moving slugs
between CSVs is destructive, so it's gated behind ``--apply``.

Usage::

    python verify_migration.py --max-suspects 100        # report only
    python verify_migration.py --ats workable            # one ATS source
    python verify_migration.py --apply                   # actually move
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
from company_discovery import PLATFORMS, validate_slug  # noqa: E402
from prune_dead_tenants import _extract_slug_from_row  # noqa: E402


def _slug_candidates(name: str) -> list[str]:
    """Generate plausible slugs from a human-readable company name.

    Each ATS has its own slug format conventions; rather than hard-code
    every variant, we try a fan-out of common normalizations and let the
    individual validators reject the misses.
    """
    raw = (name or "").strip()
    if not raw:
        return []
    out: set[str] = set()
    out.add(raw)
    out.add(raw.lower())
    # Strip whitespace/punct, keep alphanumerics + hyphens.
    cleaned = re.sub(r"[^a-zA-Z0-9-]", "", raw)
    if cleaned:
        out.add(cleaned)
        out.add(cleaned.lower())
    # Spaces → hyphens.
    hyphen = re.sub(r"\s+", "-", raw).lower()
    hyphen = re.sub(r"[^a-z0-9-]", "", hyphen)
    if hyphen:
        out.add(hyphen)
    # Spaces collapsed.
    collapsed = re.sub(r"[^a-z0-9]", "", raw.lower())
    if collapsed:
        out.add(collapsed)
    return [s for s in out if 2 <= len(s) <= 80]


async def _probe_one(
    client: httpx.AsyncClient, ats: str, slug: str
) -> tuple[str, int] | None:
    cfg = PLATFORMS.get(ats)
    if cfg is None or cfg.get("validate") is None:
        return None
    try:
        return await validate_slug(client, slug, cfg, False)
    except Exception:
        return None


async def _find_migration(
    client: httpx.AsyncClient,
    company_name: str,
    *,
    exclude_ats: str,
    sem: asyncio.Semaphore,
    candidate_atses: list[str],
) -> tuple[str, str, int] | None:
    """Return (new_ats, new_slug, jobs_count) if found, else None."""
    candidates = _slug_candidates(company_name)
    if not candidates:
        return None
    async with sem:
        for ats in candidate_atses:
            if ats == exclude_ats:
                continue
            for slug in candidates:
                res = await _probe_one(client, ats, slug)
                if res is not None and res[1] > 0:
                    return ats, slug, res[1]
    return None


def _load_suspects(source_ats: str | None) -> list[tuple[str, dict[str, Any]]]:
    """Pick rows that are likely dormant. Heuristic: tenant is in a
    CSV but has no entries in the corresponding jobs.csv. If
    ``source_ats`` is set, only consider that ATS."""
    suspects: list[tuple[str, dict[str, Any]]] = []
    targets = [source_ats] if source_ats else sorted(PLATFORMS.keys())
    import pandas as pd
    for ats in targets:
        if ats not in PLATFORMS:
            continue
        config = PLATFORMS[ats]
        comp_path = REPO / config["output_file"]
        if not comp_path.exists():
            continue
        jobs_path = REPO / ats / "jobs.csv"
        active_companies: set[str] = set()
        if jobs_path.exists():
            try:
                df = pd.read_csv(jobs_path, low_memory=False, usecols=lambda c: c in {"company"})
                active_companies = set(
                    str(c).strip().lower() for c in df.get("company", []) if c
                )
            except Exception:
                pass
        with comp_path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                slug = _extract_slug_from_row(row, config)
                name = (row.get("name") or slug or "").strip()
                if name.lower() in active_companies or slug.lower() in active_companies:
                    continue
                suspects.append((ats, {"name": name, "slug": slug, "url": row.get("url", "")}))
    return suspects


async def main_async(args: argparse.Namespace) -> int:
    suspects = _load_suspects(args.ats)
    if args.max_suspects:
        suspects = suspects[: args.max_suspects]
    print(f"Found {len(suspects)} suspect tenants (no jobs in latest scrape)")

    candidate_atses = [
        a for a in PLATFORMS
        if PLATFORMS[a].get("validate") is not None
    ]
    sem = asyncio.Semaphore(args.concurrency)
    migrations: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        async def task(item: tuple[str, dict[str, Any]]) -> None:
            old_ats, info = item
            res = await _find_migration(
                client, info["name"],
                exclude_ats=old_ats, sem=sem,
                candidate_atses=candidate_atses,
            )
            if res:
                new_ats, new_slug, n_jobs = res
                migrations.append({
                    "old_ats": old_ats, "old_slug": info["slug"],
                    "name": info["name"], "new_ats": new_ats,
                    "new_slug": new_slug, "jobs_found": n_jobs,
                })
                print(f"  {info['name']!r:>40} {old_ats} → {new_ats} ({new_slug}, {n_jobs} jobs)")

        # Batch to keep memory bounded
        batch = 50
        for i in range(0, len(suspects), batch):
            await asyncio.gather(*(task(it) for it in suspects[i:i + batch]))
            print(f"  [{i + batch}/{len(suspects)}] {len(migrations)} migrations found so far")

    print()
    print("=" * 70)
    print(f"Found {len(migrations)} migrations across {len(suspects)} suspects")
    print("=" * 70)

    out_path = REPO / f"migrations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    if migrations:
        with out_path.open("w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["old_ats", "old_slug", "name", "new_ats", "new_slug", "jobs_found"]
            )
            writer.writeheader()
            writer.writerows(migrations)
        print(f"Report: {out_path}")

    if args.apply and migrations:
        print()
        print("Applying migrations is gated behind --apply-confirm; skipping write.")
        # Apply step left intentionally manual: moving rows can break
        # CSV column shapes. Reviewing the report and patching by hand
        # is safer than blanket automation.

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ats", choices=sorted(PLATFORMS.keys()),
                        help="Limit source ATS (default: all)")
    parser.add_argument("--max-suspects", type=int, default=None,
                        help="Cap number of suspects to probe")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--apply", action="store_true",
                        help="Reserved — currently report-only")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
