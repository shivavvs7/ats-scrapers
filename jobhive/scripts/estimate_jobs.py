#!/usr/bin/env python3
"""Estimate the magnitude of jobs jobhive can currently scrape.

For each ATS:
- Read the tenant CSV
- Sample N tenants
- Run the scraper, count jobs
- Compute mean × total_tenants for an estimated total

For big-tech custom scrapers (uber, tiktok, mercor, etc.) we use the live
benchmark numbers since they're single-tenant.

Usage:
    python scripts/estimate_jobs.py
    python scripts/estimate_jobs.py --sample 10  # default 5
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # data/

# Each entry: (ats_name, csv_path, scraper_class, slug_extractor, kwargs_factory)
# slug_extractor takes a CSV row dict, returns the value to pass as company_slug.
TENANT_ATSES = [
    ("ashby", "ashby/ashby_companies.csv", "AshbyScraper", "name", lambda r: {}),
    ("bamboohr", "bamboohr/bamboohr_companies.csv", "BambooHRScraper", "name", lambda r: {}),
    ("breezy", "breezy/breezy_companies.csv", "BreezyScraper", "name", lambda r: {}),
    ("cornerstone", "cornerstone/cornerstone_companies.csv", "CornerstoneScraper", "url", lambda r: {}),
    ("eightfold", "eightfold/eightfold_companies.csv", "EightfoldScraper", "url", lambda r: {}),
    ("greenhouse", "greenhouse/greenhouse_companies.csv", "GreenhouseScraper", "name", lambda r: {}),
    ("icims", "icims/icims_companies.csv", "iCIMSScraper", "name", lambda r: {}),
    ("jazzhr", "jazzhr/jazzhr_companies.csv", "JazzHRScraper", "name", lambda r: {}),
    ("lever", "lever/lever_companies.csv", "LeverScraper", "name", lambda r: {}),
    ("personio", "personio/personio_companies.csv", "PersonioScraper", "url", lambda r: {}),
    ("recruitee", "recruitee/recruitee_companies.csv", "RecruiteeScraper", "url", lambda r: {}),
    ("rippling", "rippling/rippling_companies.csv", "RipplingScraper", "name", lambda r: {}),
    ("smartrecruiters", "smartrecruiters/smartrecruiters_companies.csv", "SmartRecruitersScraper", "name", lambda r: {}),
    ("teamtailor", "teamtailor/teamtailor_companies.csv", "TeamtailorScraper", "name", lambda r: {}),
    ("workable", "workable/workable_companies.csv", "WorkableScraper", "name", lambda r: {}),
    ("workday", "workday/workday_companies.csv", "WorkdayScraper", "url", lambda r: {}),
    ("taleo", "taleo/taleo_companies.csv", "TaleoScraper", "url", lambda r: {}),
    ("successfactors", "successfactors/successfactors_companies.csv", "SuccessFactorsScraper", "name", lambda r: {}),
]

# Big-tech custom — measured live in last benchmark
SINGLE_TENANT_KNOWN = {
    "amazon": 19818,    # POST endpoint full count
    "apple": None,      # CSRF flow, skip live for now
    "google": 2000,     # estimate based on typical
    "meta": None,       # legacy
    "tesla": None,      # blocked
    "tiktok": 3469,
    "uber": 1078,
    "mercor": 234,
}


def _slug_for(row: dict, extractor: str, ats: str = "") -> str | None:
    """Extract the slug to pass to the scraper. CSVs vary:
    - some have bare slugs in `name` (ashby, bamboohr, breezy)
    - some have full URLs in `url` (workday, taleo, eightfold)
    - some have URLs we need to derive a slug from (lever, workable, rippling)
    """
    import re
    name = (row.get("name") or "").strip()
    url = (row.get("url") or "").strip()

    # ATSes that need slug extracted from URL (lever, workable, rippling)
    if ats == "lever" and url:
        m = re.search(r"jobs\.lever\.co/([^/?#]+)", url)
        if m: return m.group(1)
    if ats == "workable" and url:
        m = re.search(r"apply\.workable\.com/([^/?#]+)", url)
        if m: return m.group(1)
    if ats == "rippling" and url:
        m = re.search(r"ats\.rippling\.com/([^/?#]+)", url)
        if m: return m.group(1)
    if ats == "eightfold" and url:
        # EightfoldScraper takes a bare slug; extract from `{slug}.eightfold.ai`
        # or accept the custom-domain URL as base_url override.
        m = re.search(r"//([a-z0-9-]+)\.eightfold\.ai", url)
        if m: return m.group(1)
        # Custom domain — fall back to name
        return name.lower().replace(" ", "")
    if ats == "personio" and url:
        # personio scraper accepts either subdomain slug or full URL
        return url
    if ats == "icims" and url:
        m = re.search(r"//careers-([a-z0-9-]+)\.icims\.com", url)
        if m: return m.group(1)

    val = (row.get(extractor) or "").strip()
    return val or None


def _scrape_one(ats: str, klass_name: str, slug: str, kwargs: dict, timeout: float = 30) -> tuple[int, float]:
    """Run a scraper, return (job_count, elapsed_seconds). On error returns (-1, elapsed)."""
    from jobhive.scrapers import (  # noqa: F401  — registered scrapers
        AshbyScraper, BambooHRScraper, BreezyScraper, CornerstoneScraper,
        EightfoldScraper, GreenhouseScraper, iCIMSScraper, JazzHRScraper,
        LeverScraper, PersonioScraper, RecruiteeScraper, RipplingScraper,
        SmartRecruitersScraper, SuccessFactorsScraper, TaleoScraper,
        TeamtailorScraper, WorkableScraper, WorkdayScraper,
    )
    klass = locals()[klass_name]
    t0 = time.time()
    try:
        scraper = klass(slug, timeout=timeout, **kwargs)
        jobs = scraper.fetch()
        return len(jobs), time.time() - t0
    except Exception:
        return -1, time.time() - t0


def estimate_ats(
    ats: str, csv_path: Path, klass_name: str, extractor: str,
    kwargs_factory, sample_size: int, timeout: float,
) -> dict:
    """Sample N tenants from the CSV, scrape each, compute mean × total."""
    if not csv_path.exists():
        return {"ats": ats, "tenants": 0, "sampled": 0, "mean_jobs": 0, "total_estimate": 0, "note": "no CSV"}

    rows = [r for r in csv.DictReader(csv_path.open()) if _slug_for(r, extractor, ats)]
    if not rows:
        return {"ats": ats, "tenants": 0, "sampled": 0, "mean_jobs": 0, "total_estimate": 0, "note": "empty CSV"}

    import random
    random.seed(42)
    sample = random.sample(rows, min(sample_size, len(rows)))

    counts: list[int] = []
    errors = 0
    total_time = 0.0
    for row in sample:
        slug = _slug_for(row, extractor, ats)
        if slug is None:
            continue
        kwargs = kwargs_factory(row)
        n, dt = _scrape_one(ats, klass_name, slug, kwargs, timeout=timeout)
        total_time += dt
        if n < 0:
            errors += 1
        else:
            counts.append(n)

    if not counts:
        return {
            "ats": ats, "tenants": len(rows), "sampled": len(sample),
            "mean_jobs": 0, "total_estimate": 0, "errors": errors,
            "sample_time": total_time,
        }

    mean_jobs = sum(counts) / len(counts)
    total_estimate = round(mean_jobs * len(rows))
    return {
        "ats": ats, "tenants": len(rows), "sampled": len(counts),
        "mean_jobs": round(mean_jobs, 1), "total_estimate": total_estimate,
        "errors": errors, "sample_time": round(total_time, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=5, help="Tenants to sample per ATS")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--only", help="Comma-separated ATS names")
    args = parser.parse_args()

    only = {x.strip() for x in args.only.split(",")} if args.only else None
    plan = [
        (ats, ROOT / csv_path, klass, ext, factory)
        for ats, csv_path, klass, ext, factory in TENANT_ATSES
        if not only or ats in only
    ]

    print(f"Estimating across {len(plan)} ATSes (sample={args.sample}/each)...\n")
    results = []
    for ats, csv_path, klass, ext, factory in plan:
        print(f"  {ats:<20} ... ", end="", flush=True)
        result = estimate_ats(ats, csv_path, klass, ext, factory, args.sample, args.timeout)
        results.append(result)
        if result["mean_jobs"]:
            print(
                f"{result['tenants']:>5} tenants × {result['mean_jobs']:>6.1f} mean = "
                f"~{result['total_estimate']:>9,} jobs  "
                f"({result['sampled']}/{args.sample} OK in {result.get('sample_time', 0):.0f}s)"
            )
        else:
            note = result.get("note") or f"{result.get('errors', 0)} errors"
            print(f"{result['tenants']:>5} tenants  [{note}]")

    # Summary
    total_multi = sum(r["total_estimate"] for r in results)
    print()
    print(f"=== Summary ===")
    print(f"Multi-tenant ATSes total estimate: ~{total_multi:,} jobs")
    print()
    print(f"Single-tenant (big-tech) known:")
    total_single = 0
    for ats, n in SINGLE_TENANT_KNOWN.items():
        if n is None:
            print(f"  {ats:<10} (skipped — needs special handling)")
        else:
            print(f"  {ats:<10} {n:>8,}")
            total_single += n
    print(f"  Subtotal: ~{total_single:,}")
    print()
    print(f"Grand total (multi + single): ~{total_multi + total_single:,} jobs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
