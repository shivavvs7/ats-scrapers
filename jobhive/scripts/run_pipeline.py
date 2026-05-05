#!/usr/bin/env python3
"""Generic pipeline runner: scrape every tenant of an ATS and write one CSV.

Used by ``full_pipeline.sh`` for ATSes that don't have a legacy
``data/{ats}/main.py`` — scrapers that live only in jobhive.

Reads ``data/{ats}/{ats}_companies.csv``, scrapes each tenant via the
appropriate jobhive class, dedupes, and writes a flat ``data/{ats}/jobs.csv``.

Usage:
    python scripts/run_pipeline.py cornerstone
    python scripts/run_pipeline.py icims --concurrency 6
    python scripts/run_pipeline.py breezy --max-tenants 50
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from jobhive.exceptions import CompanyNotFoundError
from jobhive.models import Job
from jobhive.scrapers import (
    AmazonScraper, AppleScraper, ArbetsformedlingenScraper, AshbyScraper,
    AvatureScraper, BambooHRScraper, BreezyScraper, BundesagenturScraper,
    CornerstoneScraper,
    EightfoldScraper, GoogleScraper, GreenhouseScraper, iCIMSScraper,
    JazzHRScraper, JoinComScraper, LeverScraper, MercorScraper,
    MetaScraper, OracleScraper, PersonioScraper, PhenomScraper,
    PinpointScraper, RecruiteeScraper, RecruiterboxScraper, RipplingScraper,
    SmartRecruitersScraper, SuccessFactorsScraper, TaleoScraper,
    TeamtailorScraper, TeslaScraper, TikTokScraper, UberScraper,
    WorkableScraper, WorkdayScraper,
)


def _recruitee_slug(row: dict[str, Any]) -> str | None:
    """Recruitee tenants live at ``{slug}.recruitee.com``. CSVs sometimes
    store the human-readable name in the ``name`` column and the slug in
    the URL — always parse the URL when present."""
    url = (row.get("url") or "").strip()
    if url.startswith("http"):
        m = re.match(r"https?://([a-z0-9][a-z0-9-]+)\.recruitee\.com", url, re.IGNORECASE)
        if m:
            return m.group(1).lower()
    name = (row.get("name") or "").strip()
    return name or None


def _personio_slug(row: dict[str, Any]) -> str | None:
    url = (row.get("url") or "").strip()
    if url.startswith("http"):
        m = re.match(r"https?://([a-z0-9][a-z0-9-]+)\.jobs\.personio\.com",
                     url, re.IGNORECASE)
        if m:
            return m.group(1).lower()
    name = (row.get("name") or "").strip()
    return name or None


def _avature_slug(row: dict[str, Any]) -> str | None:
    """Avature tenants live at ``{slug}.avature.net`` (or sometimes the
    full careers URL). Extract the subdomain when a URL is present."""
    url = (row.get("url") or "").strip()
    if url.startswith("http"):
        m = re.match(r"https?://([a-z0-9][a-z0-9-]+)\.avature\.net",
                     url, re.IGNORECASE)
        if m:
            return m.group(1).lower()
    name = (row.get("name") or "").strip()
    return name or None


def _rippling_slug(row: dict[str, Any]) -> str | None:
    url = (row.get("url") or "").strip()
    if url.startswith("http"):
        m = re.match(r"https?://ats\.rippling\.com/([a-z0-9][a-z0-9-]+)",
                     url, re.IGNORECASE)
        if m:
            return m.group(1).lower()
    name = (row.get("name") or "").strip()
    return name or None


def _workable_slug(row: dict[str, Any]) -> str | None:
    url = (row.get("url") or "").strip()
    if url.startswith("http"):
        m = re.match(r"https?://apply\.workable\.com/([^/?#]+)",
                     url, re.IGNORECASE)
        if m:
            # Workable tenants are case-sensitive in the URL but lowercased
            # in the API; ``apply.workable.com`` is permissive.
            return m.group(1)
    name = (row.get("name") or "").strip()
    return name or None


def _lever_slug(row: dict[str, Any]) -> str | None:
    url = (row.get("url") or "").strip()
    if url.startswith("http"):
        m = re.match(r"https?://jobs\.lever\.co/([^/?#]+)", url, re.IGNORECASE)
        if m:
            return m.group(1).lower()
    name = (row.get("name") or "").strip()
    return name or None


def _greenhouse_slug(row: dict[str, Any]) -> str | None:
    url = (row.get("url") or "").strip()
    if url.startswith("http"):
        m = re.match(
            r"https?://(?:job-boards|boards)\.greenhouse\.io/([^/?#]+)",
            url, re.IGNORECASE,
        )
        if m:
            return m.group(1).lower()
    name = (row.get("name") or "").strip()
    return name or None


def _ashby_slug(row: dict[str, Any]) -> str | None:
    url = (row.get("url") or "").strip()
    if url.startswith("http"):
        m = re.match(r"https?://jobs\.ashbyhq\.com/([^/?#]+)", url, re.IGNORECASE)
        if m:
            return m.group(1).lower()
    name = (row.get("name") or "").strip()
    return name or None


def _icims_slug(row: dict[str, Any]) -> str | None:
    """iCIMS rows can have a bare slug in `name` or a `careers-{slug}.icims.com`
    URL. Either form is accepted by the scraper, but normalize to slug."""
    url = (row.get("url") or "").strip()
    if url:
        m = re.search(r"//careers-([a-z0-9-]+)\.icims\.com", url)
        if m:
            return m.group(1)
        m = re.search(r"//uscareers-([a-z0-9-]+)\.icims\.com", url)
        if m:
            # Pass the full URL so the scraper preserves the uscareers- prefix.
            return url.split("?", 1)[0].rstrip("/")
    return (row.get("name") or "").strip() or None


# Per-ATS config:
# - scraper: the jobhive class
# - slug: callable turning a CSV row into `company_slug`
# - kwargs (optional): callable returning additional kwargs for the scraper
#   (used by Phenom which needs `locale` and `country` per tenant)
# - csv: tenant CSV path (relative to data/)
# - output: jobs CSV output path
CONFIGS: dict[str, dict[str, Any]] = {
    "cornerstone": {
        "scraper": CornerstoneScraper,
        "slug": lambda r: r.get("url") or r.get("name"),
        "csv": "cornerstone/cornerstone_companies.csv",
        "output": "cornerstone/jobs.csv",
    },
    "icims": {
        "scraper": iCIMSScraper,
        "slug": _icims_slug,
        "csv": "icims/icims_companies.csv",
        "output": "icims/jobs.csv",
    },
    "breezy": {
        "scraper": BreezyScraper,
        "slug": lambda r: r.get("name"),
        "csv": "breezy/breezy_companies.csv",
        "output": "breezy/jobs.csv",
    },
    "successfactors": {
        "scraper": SuccessFactorsScraper,
        "slug": lambda r: r.get("url") or r.get("name"),
        "csv": "successfactors/successfactors_companies.csv",
        "output": "successfactors/jobs.csv",
    },
    "taleo": {
        "scraper": TaleoScraper,
        # Taleo CSV stores bare URLs without scheme (the discovery flow
        # captures slug=full URL). The scraper needs `https://` prefix.
        "slug": lambda r: (
            (r.get("url") or "").strip()
            if (r.get("url") or "").startswith("http")
            else f"https://{(r.get('url') or '').strip()}"
            if r.get("url") else None
        ),
        "csv": "taleo/taleo_companies.csv",
        "output": "taleo/jobs.csv",
    },
    "oracle": {
        "scraper": OracleScraper,
        "slug": lambda r: r.get("url"),
        "csv": "oracle/oracle_companies.csv",
        "output": "oracle/jobs.csv",
    },
    "phenom": {
        "scraper": PhenomScraper,
        "slug": lambda r: r.get("url"),
        # Phenom needs per-tenant locale + country.
        "kwargs": lambda r: {
            "locale": r.get("locale") or "en_us",
            "country": r.get("country") or "us",
        },
        "csv": "phenom/companies.csv",
        "output": "phenom/jobs.csv",
    },
    "pinpoint": {
        "scraper": PinpointScraper,
        "slug": lambda r: r.get("name") or r.get("url"),
        "csv": "pinpoint/pinpoint_companies.csv",
        "output": "pinpoint/jobs.csv",
    },
    "recruiterbox": {
        "scraper": RecruiterboxScraper,
        "slug": lambda r: r.get("name") or r.get("url"),
        "csv": "recruiterbox/recruiterbox_companies.csv",
        "output": "recruiterbox/jobs.csv",
    },
    "workday": {
        # Workday's slug is the FULL careers URL (the scraper parses the
        # company/instance/site components). The CSV stores `url` directly.
        "scraper": WorkdayScraper,
        "slug": lambda r: (r.get("url") or "").strip() or None,
        "csv": "workday/workday_companies.csv",
        "output": "workday/jobs.csv",
    },
    "bamboohr": {
        "scraper": BambooHRScraper,
        "slug": lambda r: (r.get("name") or "").strip() or None,
        "csv": "bamboohr/bamboohr_companies.csv",
        "output": "bamboohr/jobs.csv",
    },
    "teamtailor": {
        "scraper": TeamtailorScraper,
        "slug": lambda r: (r.get("name") or "").strip() or None,
        "csv": "teamtailor/teamtailor_companies.csv",
        "output": "teamtailor/jobs.csv",
    },
    "jazzhr": {
        "scraper": JazzHRScraper,
        # JazzHR sites are Cloudflare-protected — the scraper auto-falls
        # back to httpcloak under client_kind="auto".
        "slug": lambda r: (r.get("name") or "").strip() or None,
        "csv": "jazzhr/jazzhr_companies.csv",
        "output": "jazzhr/jobs.csv",
    },
    "recruitee": {
        "scraper": RecruiteeScraper,
        # Recruitee CSVs mix human names ("5280 High School") with the
        # actual subdomain ("5280highschool"). Always derive the slug
        # from the URL when one is present.
        "slug": _recruitee_slug,
        "csv": "recruitee/recruitee_companies.csv",
        "output": "recruitee/jobs.csv",
    },
    "ashby": {
        "scraper": AshbyScraper,
        "slug": _ashby_slug,
        "csv": "ashby/ashby_companies.csv",
        "output": "ashby/jobs.csv",
    },
    "lever": {
        "scraper": LeverScraper,
        "slug": _lever_slug,
        "csv": "lever/lever_companies.csv",
        "output": "lever/jobs.csv",
    },
    "greenhouse": {
        "scraper": GreenhouseScraper,
        "slug": _greenhouse_slug,
        "csv": "greenhouse/greenhouse_companies.csv",
        "output": "greenhouse/jobs.csv",
    },
    "workable": {
        "scraper": WorkableScraper,
        "slug": _workable_slug,
        "csv": "workable/workable_companies.csv",
        "output": "workable/jobs.csv",
    },
    "smartrecruiters": {
        "scraper": SmartRecruitersScraper,
        # SmartRecruiters slugs are case-sensitive (e.g. ``Dominos``,
        # not ``dominos``). Discovery preserves case via
        # ``preserve_case`` — pass the name column verbatim.
        "slug": lambda r: (r.get("name") or "").strip() or None,
        "csv": "smartrecruiters/smartrecruiters_companies.csv",
        "output": "smartrecruiters/jobs.csv",
    },
    "personio": {
        "scraper": PersonioScraper,
        "slug": _personio_slug,
        "csv": "personio/personio_companies.csv",
        "output": "personio/jobs.csv",
    },
    "rippling": {
        "scraper": RipplingScraper,
        "slug": _rippling_slug,
        "csv": "rippling/rippling_companies.csv",
        "output": "rippling/jobs.csv",
    },
    "avature": {
        "scraper": AvatureScraper,
        "slug": _avature_slug,
        "csv": "avature/avature_companies.csv",
        "output": "avature/jobs.csv",
    },
    "join_com": {
        "scraper": JoinComScraper,
        "slug": lambda r: (r.get("name") or "").strip() or None,
        "csv": "join_com/join_com_companies.csv",
        "output": "join_com/jobs.csv",
    },
    "mercor": {
        "scraper": MercorScraper,
        # Mercor is a single-tenant scraper — slug is ignored.
        "slug": lambda r: "mercor",
        "csv": "mercor/mercor_companies.csv",
        "output": "mercor/jobs.csv",
    },
    # ---- Single-tenant big-tech scrapers (singleton mode) -----------------
    # Each big-tech employer runs its own bespoke careers system. These
    # scrapers ignore the slug (or use a fixed one) — wire them through
    # the runner via ``singleton: True`` so we don't need a one-row CSV
    # per company. Output goes to ``{ats}/jobs.csv``.
    "amazon": {
        "scraper": AmazonScraper, "singleton": True,
        "output": "amazon/jobs.csv",
    },
    "apple": {
        "scraper": AppleScraper, "singleton": True,
        "output": "apple/jobs.csv",
    },
    "google": {
        "scraper": GoogleScraper, "singleton": True,
        "output": "google/jobs.csv",
    },
    "meta": {
        "scraper": MetaScraper, "singleton": True,
        "output": "meta/jobs.csv",
    },
    "tesla": {
        "scraper": TeslaScraper, "singleton": True,
        "output": "tesla/jobs.csv",
    },
    "tiktok": {
        "scraper": TikTokScraper, "singleton": True,
        "output": "tiktok/jobs.csv",
    },
    "uber": {
        "scraper": UberScraper, "singleton": True,
        "output": "uber/jobs.csv",
    },
    "bundesagentur": {
        # German federal employment agency — official, public, ~1M+ jobs.
        # Single-source aggregator; subdivides internally by berufsfeld
        # (job category) to bypass the 10k pagination cap.
        "scraper": BundesagenturScraper, "singleton": True,
        "output": "bundesagentur/jobs.csv",
    },
    "arbetsformedlingen": {
        # Sweden's federal employment service — public JSON API. ~46k
        # active jobs, fanned out across 21 regions to bypass the 10k cap.
        "scraper": ArbetsformedlingenScraper, "singleton": True,
        "output": "arbetsformedlingen/jobs.csv",
    },
    "eightfold": {
        "scraper": EightfoldScraper,
        # CSV has either a slug (most tenants → ``{slug}.eightfold.ai``) or a
        # full custom-domain URL (``apply.careers.{co}.com``). Pass the slug
        # column verbatim; for full URLs we extract the slug and let the
        # ``base_url`` kwarg do the override.
        "slug": lambda r: (
            (r.get("slug") or r.get("url") or r.get("name") or "")
            .strip()
            .replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
            .split(".")[0]
            or None
        ),
        "kwargs": lambda r: _eightfold_kwargs(r),
        "csv": "eightfold/eightfold_companies.csv",
        "output": "eightfold/jobs.csv",
    },
}


def _eightfold_kwargs(row: dict[str, Any]) -> dict[str, Any]:
    """Build Eightfold-specific overrides from a CSV row.

    - ``url`` (when full https://...) → ``base_url`` override (custom domains).
    - ``domain`` column → API ``domain`` parameter.
    - Otherwise default to ``{slug}.eightfold.ai`` and ``{slug}.com``.
    """
    kw: dict[str, Any] = {}
    raw_url = (row.get("url") or "").strip()
    if raw_url.startswith("http"):
        kw["base_url"] = raw_url.rstrip("/")
    domain = (row.get("domain") or "").strip()
    if domain:
        kw["domain"] = domain
    name = (row.get("name") or "").strip()
    if name:
        kw["company_name"] = name
    return kw

DATA_ROOT = Path(__file__).resolve().parent.parent.parent  # → data/

JOB_CSV_FIELDS = [
    "url", "title", "company", "ats_type", "ats_id", "location",
    "is_remote", "salary_min", "salary_max", "salary_currency",
    "salary_period", "salary_summary", "employment_type", "seniority",
    "department", "team", "description", "posted_at",
    "requisition_id", "apply_url", "commitment", "raw",
]


def _job_to_row(job: Job) -> dict[str, Any]:
    """Flatten a Job to CSV-friendly fields. ``raw`` is JSON-serialized."""
    raw_json = ""
    if job.raw:
        try:
            raw_json = json.dumps(job.raw, default=str, ensure_ascii=False)[:5000]
        except (TypeError, ValueError):
            raw_json = ""
    return {
        "url": str(job.url),
        "title": job.title,
        "company": job.company,
        "ats_type": job.ats_type.value,
        "ats_id": job.ats_id,
        "location": job.location or "",
        "is_remote": "" if job.is_remote is None else str(job.is_remote).lower(),
        "salary_min": "" if job.salary_min is None else job.salary_min,
        "salary_max": "" if job.salary_max is None else job.salary_max,
        "salary_currency": job.salary_currency or "",
        "salary_period": job.salary_period or "",
        "salary_summary": job.salary_summary or "",
        "employment_type": job.employment_type or "",
        "seniority": job.seniority or "",
        "department": job.department or "",
        "team": job.team or "",
        "description": (job.description or "")[:500].replace("\n", " "),
        "posted_at": job.posted_at.isoformat() if job.posted_at else "",
        "requisition_id": job.requisition_id or "",
        "apply_url": str(job.apply_url) if job.apply_url else "",
        "commitment": job.commitment or "",
        "raw": raw_json,
    }


async def _run_scraper(scraper_cls, slug, kwargs=None, timeout=30) -> tuple[str, list[Job], str | None]:
    """Run one scraper in a thread (most are sync). Returns (slug, jobs, error_or_None)."""
    extra = kwargs or {}

    def _run() -> list[Job]:
        return scraper_cls(slug, timeout=timeout, **extra).fetch()

    try:
        jobs = await asyncio.to_thread(_run)
        return slug, jobs, None
    except CompanyNotFoundError:
        return slug, [], "not_found"
    except Exception as exc:
        return slug, [], f"{type(exc).__name__}: {str(exc)[:120]}"


async def run(ats: str, concurrency: int, max_tenants: int | None, timeout: float) -> int:
    cfg = CONFIGS[ats]

    targets: list[tuple[str, dict[str, Any]]] = []
    if cfg.get("singleton"):
        # Single-tenant scraper (big-tech bespoke careers). No CSV — call
        # the scraper once with the ATS name as a placeholder slug; the
        # scraper itself ignores it (each company has its own private API).
        targets = [(ats, {})]
    else:
        csv_path = DATA_ROOT / cfg["csv"]
        if not csv_path.exists():
            print(f"[{ats}] No tenant CSV at {csv_path}; nothing to scrape.")
            return 0
        rows = list(csv.DictReader(csv_path.open()))
        kwargs_factory = cfg.get("kwargs")
        for r in rows:
            slug = cfg["slug"](r)
            if slug:
                kw = kwargs_factory(r) if kwargs_factory else {}
                targets.append((slug, kw))

    if max_tenants:
        targets = targets[:max_tenants]

    print(f"[{ats}] Scraping {len(targets)} tenants (concurrency={concurrency}, timeout={timeout}s)")
    sem = asyncio.Semaphore(concurrency)
    counts = {"success": 0, "not_found": 0, "error": 0, "jobs": 0}

    output_path = DATA_ROOT / cfg["output"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    seen_keys: set[tuple[str, str]] = set()  # (company, ats_id) for cross-tenant dedup

    t0 = time.time()
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=JOB_CSV_FIELDS)
        writer.writeheader()

        async def task(slug: str, kw: dict[str, Any]) -> None:
            async with sem:
                _, jobs, err = await _run_scraper(cfg["scraper"], slug, kw, timeout)
            if err == "not_found":
                counts["not_found"] += 1
                return
            if err:
                counts["error"] += 1
                return
            counts["success"] += 1
            for job in jobs:
                key = (job.company, job.ats_id)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                writer.writerow(_job_to_row(job))
                counts["jobs"] += 1

        # Process tasks in batches and flush periodically
        batch_size = 50
        for i in range(0, len(targets), batch_size):
            batch = targets[i:i + batch_size]
            await asyncio.gather(*(task(s, kw) for s, kw in batch))
            f.flush()
            elapsed = time.time() - t0
            print(
                f"  [{ats}] processed {min(i + batch_size, len(targets))}/{len(targets)} "
                f"tenants in {elapsed:.0f}s — "
                f"{counts['success']} OK, {counts['not_found']} not-found, "
                f"{counts['error']} errors, {counts['jobs']:,} jobs"
            )

    elapsed = time.time() - t0
    print(
        f"[{ats}] Done in {elapsed:.0f}s: {counts['jobs']:,} jobs from "
        f"{counts['success']}/{len(targets)} tenants → {output_path}"
    )
    return 0 if counts["error"] < len(targets) // 2 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ats", choices=sorted(CONFIGS.keys()))
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--max-tenants", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    return asyncio.run(run(args.ats, args.concurrency, args.max_tenants, args.timeout))


if __name__ == "__main__":
    sys.exit(main())
