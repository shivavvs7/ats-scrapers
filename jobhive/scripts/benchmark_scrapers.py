#!/usr/bin/env python3
"""Benchmark every jobhive scraper against a known-good tenant.

For each ATS:
- jobs returned
- wall-clock time
- throughput (jobs/sec)
- status (OK / FAIL with error tail)

The tenants are chosen to be small/medium and currently active, so the
benchmark finishes in a few minutes rather than 30+. Big-tech custom
scrapers (Amazon, Google) are run with explicit page caps so they don't
dominate runtime.

Usage:
    python scripts/benchmark_scrapers.py
    python scripts/benchmark_scrapers.py --only ashby,greenhouse,lever
    python scripts/benchmark_scrapers.py --skip amazon,google
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from dataclasses import dataclass

from jobhive.scrapers import (
    AmazonScraper,
    AshbyScraper,
    AvatureScraper,
    BambooHRScraper,
    EightfoldScraper,
    GemScraper,
    GoogleScraper,
    GreenhouseScraper,
    JazzHRScraper,
    JoinComScraper,
    LeverScraper,
    MercorScraper,
    OracleScraper,
    PersonioScraper,
    PhenomScraper,
    RecruiteeScraper,
    RipplingScraper,
    SmartRecruitersScraper,
    TeamtailorScraper,
    TikTokScraper,
    UberScraper,
    WorkableScraper,
    WorkdayScraper,
)


@dataclass
class BenchSpec:
    """One row in the benchmark plan."""
    ats: str
    factory: callable  # () -> BaseScraper instance
    note: str = ""


# ---------------------------------------------------------------- specs --

# Tenants picked for: (a) currently active, (b) small enough that the bench
# finishes in seconds, (c) representative of the typical jobhive use case.
# For Amazon/Google we cap pages — full scrapes take minutes.

SPECS: list[BenchSpec] = [
    # --- Multi-tenant ATSes (job board APIs) ---
    BenchSpec("greenhouse", lambda: GreenhouseScraper("anthropic", timeout=30)),
    BenchSpec("lever", lambda: LeverScraper("anthropic", timeout=30)),
    BenchSpec("ashby", lambda: AshbyScraper("ramp", timeout=30)),
    BenchSpec("workable", lambda: WorkableScraper("1000heads", timeout=30)),
    BenchSpec("smartrecruiters", lambda: SmartRecruitersScraper("Schaeffler", timeout=30)),
    BenchSpec("rippling", lambda: RipplingScraper("rippling", timeout=30)),
    BenchSpec("personio", lambda: PersonioScraper("https://1komma5grad.jobs.personio.com", timeout=30)),
    BenchSpec("recruitee", lambda: RecruiteeScraper("12build", timeout=30)),
    BenchSpec("gem", lambda: GemScraper("11x-ai", timeout=30)),
    BenchSpec("workday", lambda: WorkdayScraper("https://accenture.wd103.myworkdayjobs.com/accenturecareers", timeout=60), note="big tenant"),
    BenchSpec("oracle", lambda: OracleScraper("https://eeho.fa.us2.oraclecloud.com", timeout=30)),
    BenchSpec("avature", lambda: _avature_capped()),

    # --- HTML-only ATSes ---
    BenchSpec("bamboohr", lambda: BambooHRScraper("ashememorial", timeout=30)),
    BenchSpec("teamtailor", lambda: TeamtailorScraper("forenadecare", timeout=30)),
    BenchSpec("jazzhr", lambda: JazzHRScraper("perkspot12", timeout=30)),
    BenchSpec("join_com", lambda: JoinComScraper("daimler-truck", timeout=30)),

    # --- Eightfold (multi-tenant) ---
    BenchSpec("eightfold", lambda: EightfoldScraper("dolby", timeout=30), note="100ish jobs"),

    # --- Phenom (per-tenant config) ---
    BenchSpec("phenom", lambda: PhenomScraper("https://jobs.bell.ca", locale="en_ca", country="ca", timeout=30)),

    # --- Big-tech custom (capped) ---
    BenchSpec("amazon", lambda: _amazon_capped(), note="capped at 1 page (~100 jobs)"),
    BenchSpec("google", lambda: _google_capped(), note="capped at 3 pages (~60 jobs)"),

    # --- Big-tech custom (single-tenant, run as-is) ---
    BenchSpec("uber", lambda: UberScraper("uber", timeout=60)),
    BenchSpec("tiktok", lambda: TikTokScraper("tiktok", timeout=60)),
    BenchSpec("mercor", lambda: MercorScraper("any", timeout=30)),

    # --- Skipped: tesla (Akamai), apple (CSRF + slow), meta (kept legacy)
]


def _amazon_capped() -> AmazonScraper:
    """Cap Amazon at one page (~100 jobs) — full scrape is 19K+ and the
    bench would take minutes."""
    s = AmazonScraper("amazon", timeout=30)
    import jobhive.scrapers.amazon as am
    am.PAGE_SIZE = 100
    am.PAGINATION_CAP = 100  # stop after one page
    return s


def _google_capped() -> GoogleScraper:
    s = GoogleScraper("google", timeout=30)
    import jobhive.scrapers.google as g
    g.MAX_PAGES = 3
    return s


def _avature_capped() -> AvatureScraper:
    """Bloomberg has ~500 jobs; full scrape is 30s. Cap at 5 pages."""
    s = AvatureScraper("bloomberg", timeout=30)
    import jobhive.scrapers.avature as av
    av.MAX_PAGES = 5
    return s


# -------------------------------------------------------------- runner --


@dataclass
class Result:
    ats: str
    jobs: int
    seconds: float
    status: str  # "OK" or "FAIL: ..."
    note: str = ""

    @property
    def rate(self) -> float:
        return self.jobs / self.seconds if self.seconds > 0 else 0


def run_one(spec: BenchSpec) -> Result:
    print(f"  {spec.ats:<18} ... ", end="", flush=True)
    t0 = time.time()
    try:
        scraper = spec.factory()
        jobs = scraper.fetch()
    except Exception as exc:
        elapsed = time.time() - t0
        msg = f"{type(exc).__name__}: {exc}"
        if len(msg) > 80:
            msg = msg[:80] + "..."
        print(f"FAIL ({elapsed:.1f}s) — {msg}")
        return Result(spec.ats, 0, elapsed, f"FAIL: {msg}", spec.note)
    elapsed = time.time() - t0
    rate = len(jobs) / elapsed if elapsed > 0 else 0
    print(f"OK    {len(jobs):>5} jobs in {elapsed:>6.2f}s ({rate:>5.1f}/s)")
    return Result(spec.ats, len(jobs), elapsed, "OK", spec.note)


def print_summary(results: list[Result]) -> None:
    print()
    print("=" * 78)
    print("Benchmark Summary")
    print("=" * 78)
    ok = [r for r in results if r.status == "OK"]
    fail = [r for r in results if r.status != "OK"]

    print(f"\n{len(ok)}/{len(results)} scrapers passed\n")
    print(f"  {'ATS':<18} {'jobs':>6}   {'time':>8}   {'jobs/s':>8}  note")
    print(f"  {'-'*18} {'-'*6}   {'-'*8}   {'-'*8}  {'-'*30}")
    for r in sorted(ok, key=lambda x: -x.rate):
        note = f"  {r.note}" if r.note else ""
        print(
            f"  {r.ats:<18} {r.jobs:>6}   {r.seconds:>7.2f}s   "
            f"{r.rate:>7.1f}/s{note}"
        )

    if fail:
        print(f"\n  Failures ({len(fail)}):")
        for r in fail:
            err = r.status.removeprefix("FAIL: ")
            print(f"    {r.ats:<18} {r.seconds:>5.1f}s   {err}")

    if ok:
        total_jobs = sum(r.jobs for r in ok)
        total_time = sum(r.seconds for r in ok)
        print(f"\n  Total: {total_jobs:,} jobs across {len(ok)} ATSes in {total_time:.1f}s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="Comma-separated ATS names to run")
    parser.add_argument("--skip", help="Comma-separated ATS names to skip")
    args = parser.parse_args()

    plan = SPECS[:]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        plan = [s for s in plan if s.ats in wanted]
    if args.skip:
        skip = {s.strip() for s in args.skip.split(",")}
        plan = [s for s in plan if s.ats not in skip]

    print(f"Running {len(plan)} scraper benchmarks...\n")
    results: list[Result] = []
    for spec in plan:
        results.append(run_one(spec))

    print_summary(results)
    return 0 if all(r.status == "OK" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
