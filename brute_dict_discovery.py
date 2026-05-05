#!/usr/bin/env python3
"""Cross-ATS brute-force discovery from a name dictionary.

Companies often have boards on multiple ATSes (active or stale). A
company we know on Greenhouse may also be on Workable / Lever / JazzHR
under a similar slug. This script takes a list of names, derives slug
candidates, and probes every target ATS — adding any verified hits to
its companies CSV.

Skips names that are already known on the target ATS (no point re-probing
existing tenants). Validation goes through ``company_discovery``'s
existing two-pass logic so the safety guarantees match.

Usage::

    python brute_dict_discovery.py --ats workable
    python brute_dict_discovery.py --ats workable --dict company_dictionary.txt
    python brute_dict_discovery.py --ats workable --concurrency 4 --max 5000
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

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
from company_discovery import PLATFORMS, validate_slug, existing_slugs_from_csv  # noqa: E402

# Per-ATS slug normalizer. Most ATSes use lowercase alphanumerics with
# hyphens; some allow longer/quirkier forms. The normalizers below match
# what each platform's discovery regex captures.
def _slug_variants(name: str, ats: str) -> list[str]:
    name = (name or "").strip()
    if not name:
        return []
    out: list[str] = []
    base = name.lower()
    # 1. Bare lowercase, no separators (most workable-style ATSes)
    pure = re.sub(r"[^a-z0-9]", "", base)
    if 2 <= len(pure) <= 60:
        out.append(pure)
    # 2. Hyphenated form (workable, lever, rippling)
    hyphen = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    if hyphen and hyphen != pure and 2 <= len(hyphen) <= 60:
        out.append(hyphen)
    # 3. ATS-specific: greenhouse/lever can have numeric/alphanumeric
    if ats in ("greenhouse", "ashby", "lever"):
        # also try the original case-preserved form for ATSes that allow it
        original = re.sub(r"[^A-Za-z0-9]", "", name)
        if original and original.lower() != pure:
            out.append(original.lower())
    # Dedupe preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for v in out:
        if v not in seen:
            seen.add(v)
            deduped.append(v)
    return deduped


async def _check(
    client: httpx.AsyncClient,
    slug: str,
    config: dict,
    sem: asyncio.Semaphore,
    *,
    attempts: int = 1,
) -> tuple[str, int] | None:
    """Validate one slug. Single-pass on first call; retry up to ``attempts``
    on transient failures."""
    last: tuple[str, int] | None = None
    for attempt in range(1, attempts + 1):
        async with sem:
            try:
                last = await validate_slug(client, slug, config, False)
            except Exception:
                last = None
        if last is not None:
            return last
        if attempt < attempts:
            await asyncio.sleep(0.8 * attempt)
    return None


async def _scan(
    ats: str,
    dictionary: list[str],
    concurrency: int,
    max_probes: int | None,
    dry_run: bool,
) -> int:
    config = PLATFORMS[ats]
    csv_path = REPO / config["output_file"]
    patterns = [re.compile(p, re.IGNORECASE) for p in config["patterns"]]
    existing = existing_slugs_from_csv(csv_path, patterns)
    print(f"[{ats}] dictionary={len(dictionary)} names | "
          f"existing={len(existing)} tenants")

    # Build (name, slug) probes, skipping already-known slugs.
    probes: list[tuple[str, str]] = []
    for name in dictionary:
        for slug in _slug_variants(name, ats):
            if slug in existing:
                continue
            probes.append((name, slug))
    # Dedup probes by slug (multiple names may map to same slug).
    seen_slugs: set[str] = set()
    deduped_probes: list[tuple[str, str]] = []
    for name, slug in probes:
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        deduped_probes.append((name, slug))

    if max_probes:
        deduped_probes = deduped_probes[:max_probes]
    print(f"[{ats}] {len(deduped_probes)} unique slug probes "
          f"(after dedup + skip-existing)")

    sem = asyncio.Semaphore(concurrency)
    hits: list[tuple[str, str, int]] = []  # (name, slug, jobs)
    started = datetime.now()
    progress_every = max(1, len(deduped_probes) // 50)

    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        # Pass 1: fast scan
        results: list[tuple[tuple[str, str], tuple[str, int] | None]] = []

        async def probe(item: tuple[str, str]) -> None:
            name, slug = item
            res = await _check(client, slug, config, sem, attempts=1)
            results.append(((name, slug), res))

        # Run in batches so we get periodic progress.
        batch_size = 200
        for i in range(0, len(deduped_probes), batch_size):
            await asyncio.gather(*(probe(it) for it in deduped_probes[i:i + batch_size]))
            elapsed = (datetime.now() - started).total_seconds()
            done = min(i + batch_size, len(deduped_probes))
            n_hits = sum(1 for _, r in results if r is not None)
            print(f"  [{ats}] {done:>5}/{len(deduped_probes)} probed in {elapsed:.0f}s — {n_hits} hits")

        confirmed: list[tuple[str, str, int]] = [
            (name, slug, res[1]) for (name, slug), res in results if res is not None
        ]

        # Pass 2: re-validate hits SEQUENTIALLY with long backoffs so that
        # stubborn rate-limited ATSes (workable, in particular) don't drop
        # real positives. Pass 1 was permissive → false positives are
        # possible; pass 2 must be strict but not strangled by 429s.
        if confirmed:
            slow_sem = asyncio.Semaphore(1)
            print(f"[{ats}] re-validating {len(confirmed)} hits sequentially")
            recheck: list[tuple[str, int] | None] = []
            for _, slug, _ in confirmed:
                res = await _check(client, slug, config, slow_sem, attempts=3)
                recheck.append(res)
                await asyncio.sleep(0.4)
            hits = [
                (name, slug, res[1] if res else 0)
                for (name, slug, _), res in zip(confirmed, recheck)
                if res is not None
            ]

    elapsed = (datetime.now() - started).total_seconds()
    print(f"[{ats}] CONFIRMED {len(hits)} new tenants in {elapsed/60:.1f} min")
    if not hits:
        return 0

    if dry_run:
        for name, slug, n in hits[:20]:
            print(f"  [dry] {name!r:>30} -> slug={slug!r:<25} jobs={n}")
        if len(hits) > 20:
            print(f"  ... and {len(hits) - 20} more")
        return 0

    # Append to CSV (additive — never overwrite).
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    with csv_path.open("a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["name", "url"])
        for name, slug, _ in hits:
            url = _public_url_for(ats, slug)
            writer.writerow([name, url])
    print(f"[{ats}] appended {len(hits)} new rows to {csv_path}")
    return len(hits)


def _public_url_for(ats: str, slug: str) -> str:
    return {
        "recruitee": f"https://{slug}.recruitee.com",
        "bamboohr": f"https://{slug}.bamboohr.com/careers",
        "teamtailor": f"https://{slug}.teamtailor.com",
        "jazzhr": f"https://{slug}.applytojob.com",
        "lever": f"https://jobs.lever.co/{slug}",
        "greenhouse": f"https://job-boards.greenhouse.io/{slug}",
        "ashby": f"https://jobs.ashbyhq.com/{slug}",
        "workable": f"https://apply.workable.com/{slug}",
        "smartrecruiters": f"https://jobs.smartrecruiters.com/{slug}",
        "rippling": f"https://ats.rippling.com/{slug}/jobs",
        "personio": f"https://{slug}.jobs.personio.com",
        "icims": f"https://careers-{slug}.icims.com",
        "breezy": f"https://{slug}.breezy.hr",
        "pinpoint": f"https://{slug}.pinpointhq.com",
        "recruiterbox": f"https://{slug}.hire.trakstar.com",
        "cornerstone": f"https://{slug}.csod.com",
    }.get(ats, slug)


async def main_async(args: argparse.Namespace) -> int:
    dict_path = Path(args.dict)
    if not dict_path.exists():
        print(f"dictionary not found: {dict_path}", file=sys.stderr)
        return 1
    dictionary = [
        line.strip() for line in dict_path.read_text().splitlines()
        if line.strip()
    ]
    targets = [args.ats] if args.ats else sorted(["workable", "jazzhr", "lever", "greenhouse"])
    grand = 0
    for ats in targets:
        if ats not in PLATFORMS:
            print(f"unknown ATS: {ats}", file=sys.stderr)
            continue
        n = await _scan(
            ats, dictionary,
            concurrency=args.concurrency,
            max_probes=args.max,
            dry_run=args.dry_run,
        )
        grand += n
    print()
    print("=" * 70)
    print(f"Grand total: {grand} new tenants discovered via dictionary brute-force")
    print("=" * 70)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ats", choices=sorted(PLATFORMS.keys()),
        help="Single ATS to scan (default: workable + jazzhr + lever + greenhouse)",
    )
    parser.add_argument(
        "--dict", default="company_dictionary.txt",
        help="Path to newline-separated names file (default: company_dictionary.txt)",
    )
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--max", type=int, default=None,
                        help="Stop after probing N candidates (smoke test)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report hits without writing")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
