#!/usr/bin/env python3
"""Single-purpose, paranoid Workable tenant validator.

Workable's ``apply.workable.com`` rate-limits *aggressively* — even
concurrency=3 from one IP triggers global 429s that get interpreted as
404 by lazy validators. This script attacks the problem from several
angles so we can confidently drop only genuinely-dead tenants:

1. **Sequential pacing.** One request at a time with jittered delays.
2. **Two endpoints per tenant.** A tenant is "alive" if EITHER passes:
   - ``GET /api/v1/widget/accounts/{slug}`` → 200 + ``name`` field
   - ``GET /{slug}`` (the public careers page) → 200 + non-empty body
3. **User-Agent rotation.** Cycle through 4 realistic browser UAs.
4. **httpcloak fallback for suspects.** Anything that fails the httpx
   path is re-checked with browser-fingerprinted TLS — this catches
   tenants whose bot detection trips on ``python-httpx``.
5. **Conservative writeback.** Only writes when we're confident.

Usage::

    python prune_workable_thorough.py                # write
    python prune_workable_thorough.py --dry-run      # preview
    python prune_workable_thorough.py --limit 200    # smoke test

A timestamped backup is written before overwriting.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
from prune_dead_tenants import _extract_slug_from_row  # noqa: E402
from company_discovery import PLATFORMS  # noqa: E402

CSV_PATH = REPO / "workable" / "workable_companies.csv"

USER_AGENTS = [
    # Modern desktop browsers — realistic, varied entropy.
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 "
    "Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
]

API_TEMPLATE = "https://apply.workable.com/api/v1/widget/accounts/{slug}"
PAGE_TEMPLATE = "https://apply.workable.com/{slug}/"
DELAY_MIN = 0.30
DELAY_MAX = 0.55


def _ua() -> str:
    return random.choice(USER_AGENTS)


async def _check_api(client: httpx.AsyncClient, slug: str) -> bool | None:
    """Return True if alive, False if confirmed dead, None if uncertain."""
    try:
        r = await client.get(
            API_TEMPLATE.format(slug=slug),
            headers={"User-Agent": _ua(), "Accept": "application/json"},
            timeout=15,
        )
    except httpx.HTTPError:
        return None
    if r.status_code == 200:
        try:
            data = r.json()
        except ValueError:
            return None
        # Real tenants have a non-empty ``name``; placeholder/dead pages
        # may 200 with empty fields.
        return bool(isinstance(data, dict) and data.get("name"))
    if r.status_code == 404:
        return False
    if r.status_code in (429, 502, 503, 504):
        return None  # transient — fall back to other paths
    return None


async def _check_page(client: httpx.AsyncClient, slug: str) -> bool | None:
    try:
        r = await client.get(
            PAGE_TEMPLATE.format(slug=slug),
            headers={"User-Agent": _ua(), "Accept": "text/html,*/*"},
            timeout=15,
            follow_redirects=False,
        )
    except httpx.HTTPError:
        return None
    if r.status_code == 200:
        # Workable's 404 page also returns 200 in some cases — guard with
        # a marker check. Real careers pages always carry the application
        # frame keywords.
        body = r.text[:5000].lower()
        if "page not found" in body or "doesn't exist" in body:
            return False
        if "workable" in body and len(body) > 500:
            return True
        return None
    if r.status_code in (301, 302):
        # Redirects to the marketing site indicate the tenant is gone.
        loc = (r.headers.get("location") or "").lower()
        if "workable.com" in loc and slug not in loc:
            return False
        return None
    if r.status_code == 404:
        return False
    if r.status_code in (429, 502, 503, 504):
        return None
    return None


async def _check_httpcloak(slug: str) -> bool | None:
    """Final resort: browser-fingerprinted TLS. Bypasses the bot detector
    that flags python-httpx requests as suspicious."""
    try:
        import httpcloak
    except ImportError:
        return None
    loop = asyncio.get_running_loop()

    def call() -> tuple[int, str]:
        try:
            r = httpcloak.get(
                API_TEMPLATE.format(slug=slug),
                timeout=15,
                headers={"User-Agent": _ua(), "Accept": "application/json"},
            )
            return r.status_code, r.text
        except Exception:
            return 0, ""

    status, text = await loop.run_in_executor(None, call)
    if status == 200:
        try:
            import json
            data = json.loads(text)
        except ValueError:
            return None
        return bool(isinstance(data, dict) and data.get("name"))
    if status == 404:
        return False
    return None


async def _verdict(client: httpx.AsyncClient, slug: str) -> bool:
    """True iff the tenant is confirmed alive across at least one path."""
    api = await _check_api(client, slug)
    if api is True:
        return True
    page = await _check_page(client, slug)
    if page is True:
        return True
    # Both came back uncertain → try httpcloak (can be slow but bypasses
    # the bot wall).
    if api is None and page is None:
        cloak = await _check_httpcloak(slug)
        if cloak is True:
            return True
        if cloak is False:
            return False
        # Two uncertain results + cloak inconclusive → keep alive (safer
        # to retain a possibly-dead tenant than to nuke a real one).
        return True
    # If api/page came back False explicitly, drop.
    if api is False and page is not True:
        return False
    if page is False and api is not True:
        return False
    # Mixed/unclear → keep alive.
    return True


async def main_async(args: argparse.Namespace) -> int:
    rows = list(csv.DictReader(CSV_PATH.open()))
    if args.limit:
        rows = rows[: args.limit]
    config = PLATFORMS["workable"]

    print(f"[workable] thorough validation of {len(rows)} tenants — "
          f"sequential, multi-endpoint, UA rotation")
    started = time.time()

    alive_indices: set[int] = set()
    progress_every = max(1, len(rows) // 20)

    async with httpx.AsyncClient(
        timeout=20, follow_redirects=False
    ) as client:
        for i, row in enumerate(rows):
            slug = _extract_slug_from_row(row, config)
            if not slug:
                continue
            if await _verdict(client, slug):
                alive_indices.add(i)
            if (i + 1) % progress_every == 0 or i + 1 == len(rows):
                pct = (i + 1) * 100 // len(rows)
                elapsed = time.time() - started
                rate = (i + 1) / elapsed if elapsed else 0
                print(
                    f"  [{pct:>3}%] {i + 1:>5}/{len(rows)} — "
                    f"{len(alive_indices):>5} alive, {(i + 1) - len(alive_indices):>5} dead "
                    f"({elapsed:.0f}s, {rate:.1f}/s)"
                )
            await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    kept = [rows[i] for i in range(len(rows)) if i in alive_indices]
    dropped = len(rows) - len(kept)
    elapsed = time.time() - started
    print()
    print(f"[workable] {len(kept)} kept / {dropped} dropped ({dropped/len(rows)*100:.1f}%) "
          f"in {elapsed/60:.1f} min")

    if args.dry_run:
        print("[workable] --dry-run: not writing")
        return 0
    if dropped == 0:
        print("[workable] nothing to drop, leaving file untouched")
        return 0

    backup = CSV_PATH.with_suffix(
        f".csv.bak_thorough_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    CSV_PATH.replace(backup)
    print(f"[workable] backup: {backup.name}")

    with CSV_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(kept)
    print(f"[workable] wrote {len(kept)} tenants → {CSV_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after N tenants (smoke test)")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
