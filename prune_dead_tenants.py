#!/usr/bin/env python3
"""Re-validate every tenant in ``data/{ats}/{ats}_companies.csv`` and drop the dead ones.

A "dead" tenant is one whose validate URL no longer returns the expected
shape — typically a 404, a redirect to a marketing page, or a Cloudflare
challenge with no fallback. Tenants that respond cleanly with **zero open
positions** are kept (they're real but currently empty).

Usage::

    python prune_dead_tenants.py greenhouse              # one ATS, write in place
    python prune_dead_tenants.py greenhouse --dry-run    # preview, don't write
    python prune_dead_tenants.py --all                   # every supported ATS
    python prune_dead_tenants.py greenhouse --httpcloak  # force browser TLS

A timestamped backup is created next to each CSV before overwriting:
``{ats}_companies.csv.bak_pruned_YYYYMMDD_HHMMSS``.

Reuses ``company_discovery.PLATFORMS`` so we never need to keep validation
logic in two places.
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

# Reuse the platform configs + per-tenant validator from discovery.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from company_discovery import PLATFORMS, validate_slug  # noqa: E402

REPO = Path(__file__).resolve().parent
DEFAULT_CONCURRENCY = 12


def _extract_slug_from_row(row: dict[str, Any], config: dict[str, Any]) -> str:
    """Resolve the tenant slug for a CSV row.

    Discovery stores ``name`` as the human-readable label (often CamelCase
    or with spaces) and ``url`` as either the full canonical careers URL
    *or* the raw slug — depending on when the file was written and whether
    it's been touched by a linter. The validator only works with the
    canonical lowercased slug.

    Strategy:
      1. If ``url`` looks like an HTTP URL, run the platform's discovery
         regex against it and pull the captured slug. Falls back to the
         raw URL when no regex matches (Workday-style: the CSV's URL IS
         the slug).
      2. If ``url`` is a bare token (no ``://``), use it as-is.
      3. Otherwise fall back to ``name``.
    """
    url = (row.get("url") or "").strip()
    if url.startswith("http"):
        for pat_str in config.get("patterns") or []:
            m = re.search(pat_str, url)
            if m:
                try:
                    slug = m.group("slug")
                except (IndexError, KeyError):
                    continue
                if not config.get("preserve_case", False):
                    slug = slug.lower()
                return slug
        # No pattern matched — use the URL minus the scheme as a last resort.
        return url
    if url:
        return url
    return (row.get("name") or "").strip()


async def _check_one(
    client: httpx.AsyncClient,
    slug: str,
    config: dict[str, Any],
    use_httpcloak: bool,
    sem: asyncio.Semaphore,
    *,
    attempts: int = 1,
) -> tuple[str, bool]:
    """Return (slug, is_alive). ``is_alive=True`` when validation succeeds —
    even if the tenant has zero current openings.

    ``attempts`` controls how many times we retry transient failures (rate
    limits, brief connection errors) before giving up. Set ``attempts=1``
    on the fast first pass; the second confirmation pass uses 3."""
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        async with sem:
            try:
                result = await validate_slug(client, slug, config, use_httpcloak)
            except Exception as exc:
                last_err = exc
                result = None
        if result is not None:
            return slug, True
        if attempt < attempts:
            await asyncio.sleep(1.5 * attempt)
    return slug, False


async def _prune(
    ats: str,
    *,
    concurrency: int,
    use_httpcloak: bool,
    dry_run: bool,
    max_drop_pct: float,
) -> tuple[int, int]:
    config = PLATFORMS[ats]
    csv_path = REPO / config["output_file"]
    if not csv_path.exists():
        print(f"[{ats}] CSV not found: {csv_path}")
        return 0, 0

    with csv_path.open() as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            print(f"[{ats}] empty CSV")
            return 0, 0
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    if not rows:
        print(f"[{ats}] no tenants in CSV")
        return 0, 0

    print(f"[{ats}] Validating {len(rows)} tenants (concurrency={concurrency}, "
          f"httpcloak={use_httpcloak or config.get('client') == 'httpcloak'})")

    # Build (row_index, slug) pairs so we can map results back even when
    # multiple rows share the same slug.
    indexed: list[tuple[int, str]] = []
    for i, r in enumerate(rows):
        s = _extract_slug_from_row(r, config)
        if s:
            indexed.append((i, s))

    # Two-pass strategy. Pass 1 is a fast wide check at full concurrency:
    # most tenants pass and we filter the candidate-dead list down. Pass 2
    # re-checks only the failures at lower concurrency with retries —
    # this is what catches rate-limited false positives. Tenants need to
    # fail BOTH passes to be considered dead.
    async with httpx.AsyncClient(
        timeout=20, follow_redirects=False
    ) as client:
        sem_fast = asyncio.Semaphore(concurrency)
        first_results = await asyncio.gather(*(
            _check_one(client, slug, config, use_httpcloak, sem_fast)
            for _, slug in indexed
        ))

        first_alive: set[int] = {
            idx for (idx, _), (_, is_alive) in zip(indexed, first_results) if is_alive
        }
        candidates_to_recheck = [
            (idx, slug) for (idx, slug), (_, is_alive) in zip(indexed, first_results)
            if not is_alive
        ]
        if candidates_to_recheck:
            print(f"[{ats}] pass 1: {len(first_alive)} alive, "
                  f"{len(candidates_to_recheck)} suspect — rechecking with retries")
            sem_slow = asyncio.Semaphore(max(2, concurrency // 4))
            second_results = await asyncio.gather(*(
                _check_one(client, slug, config, use_httpcloak, sem_slow, attempts=3)
                for _, slug in candidates_to_recheck
            ))
            for (idx, _), (_, is_alive) in zip(candidates_to_recheck, second_results):
                if is_alive:
                    first_alive.add(idx)

    kept_rows = [rows[i] for i in range(len(rows)) if i in first_alive]
    dropped = len(rows) - len(kept_rows)

    print(f"[{ats}] kept {len(kept_rows)} / dropped {dropped}")

    if dropped == 0:
        return len(rows), 0

    if dry_run:
        print(f"[{ats}] --dry-run: not writing")
        return len(rows), dropped

    drop_pct = dropped / len(rows) * 100 if rows else 0.0
    if drop_pct > max_drop_pct:
        # High drop rates almost always indicate rate-limiting on the
        # validator endpoint, not a wave of dead tenants. Refuse to
        # write — safer to skip than to nuke real tenants.
        print(
            f"[{ats}] SAFETY ABORT: drop rate {drop_pct:.1f}% exceeds "
            f"--max-drop-pct {max_drop_pct:.1f}%. Likely rate-limiting "
            f"false positives. Skipping write. Re-run with "
            f"--concurrency 4 (or lower) to bypass."
        )
        return len(rows), 0

    backup = csv_path.with_suffix(
        f".csv.bak_pruned_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    csv_path.replace(backup)
    print(f"[{ats}] backup: {backup.name}")

    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept_rows)

    print(f"[{ats}] wrote {len(kept_rows)} tenants → {csv_path}")
    return len(rows), dropped


async def main_async(args: argparse.Namespace) -> int:
    targets = sorted(PLATFORMS.keys()) if args.all else [args.platform]
    grand_total = grand_dropped = 0
    for ats in targets:
        if ats not in PLATFORMS:
            print(f"[{ats}] unknown platform; skipping")
            continue
        if PLATFORMS[ats].get("validate") is None:
            # workday has no per-tenant validator (the URLs are full search
            # URLs that change shape across instances); a separate audit
            # script handles it. Don't prune blindly.
            print(f"[{ats}] no validator — skipping (use audit script)")
            continue
        total, dropped = await _prune(
            ats,
            concurrency=args.concurrency,
            use_httpcloak=args.httpcloak,
            dry_run=args.dry_run,
            max_drop_pct=args.max_drop_pct,
        )
        grand_total += total
        grand_dropped += dropped

    print()
    print("=" * 70)
    print(f"Grand total: {grand_total} tenants checked, {grand_dropped} dropped "
          f"({grand_dropped / grand_total * 100:.1f}%)" if grand_total else "no tenants checked")
    print("=" * 70)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", nargs="?", choices=sorted(PLATFORMS.keys()))
    parser.add_argument("--all", action="store_true",
                        help="Prune every supported ATS")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report counts without writing")
    parser.add_argument("--httpcloak", action="store_true",
                        help="Force httpcloak (browser TLS) for tricky tenants")
    parser.add_argument(
        "--max-drop-pct", type=float, default=25.0,
        help="Refuse to write when drop rate exceeds this percent (default 25). "
             "Catches rate-limit false positives. Use a higher value or run "
             "with --concurrency 4 if you trust the result.",
    )
    args = parser.parse_args()

    if not args.platform and not args.all:
        parser.error("specify a platform or --all")

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
