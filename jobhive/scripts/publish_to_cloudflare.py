#!/usr/bin/env python3
"""One-shot Cloudflare publisher for the existing stapply-ai/data layout.

Picks up:
  - <repo>/<ats>/jobs.csv   for every ATS folder
  - <repo>/ai-DD-MM-YYYY.csv for dated daily snapshots
  - companies.csv if present

and pushes them to R2 under jobhive/v1/ with a manifest.

Usage:
  uv run python jobhive/scripts/publish_to_cloudflare.py [--source <dir>] [--dry-run]

Required env vars (in <repo>/.env):
  CLOUDFLARE_ACCOUNT_ID
  CLOUDFLARE_BUCKET_NAME
  CLOUDFLARE_ACCESS_KEY_ID
  CLOUDFLARE_SECRET_ACCESS_KEY
  CLOUDFLARE_PUBLIC_BASE_URL  (optional, e.g. https://storage.stapply.ai)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repo root holding <ats>/jobs.csv folders (default: parent of jobhive/)",
    )
    parser.add_argument(
        "--dated-glob",
        default=None,
        help=(
            "Glob for dated snapshots under --source. "
            "Default: today only (ai-DD-MM-YYYY.csv). "
            "Pass `ai-*.csv` to backfill every dated snapshot."
        ),
    )
    parser.add_argument(
        "--no-parquet",
        action="store_true",
        help="Skip parquet writes (CSV only — useful when pyarrow is missing)",
    )
    parser.add_argument(
        "--prune-old-dated",
        action="store_true",
        help=(
            "After uploading, delete every dated snapshot in R2 whose date is "
            "not today. Idempotent. Recommended: run once to clean up legacy "
            "backfill, then leave off (daily runs naturally accumulate)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be uploaded without writing to R2",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    log = logging.getLogger("publish")

    source: Path = args.source.resolve()
    log.info("Source directory: %s", source)

    _load_dotenv(source / ".env")

    # Make jobhive importable when running as a script before installation.
    sys.path.insert(0, str(source / "jobhive" / "src"))

    from jobhive.models import ATSType
    from jobhive.storage import DatasetPublisher, R2Client, R2Config

    ats_files = []
    for ats in ATSType:
        if ats is ATSType.CUSTOM:
            continue
        path = source / ats.value / "jobs.csv"
        if path.exists():
            ats_files.append((ats.value, path, path.stat().st_size))

    log.info("Found %d ATS slices:", len(ats_files))
    for name, path, size in ats_files:
        log.info("  %-18s %10d bytes  %s", name, size, path.relative_to(source))

    if args.dated_glob:
        glob_pattern = args.dated_glob
    else:
        from datetime import date

        today = date.today()
        glob_pattern = f"ai-{today.day:02d}-{today.month:02d}-{today.year}.csv"

    dated = sorted(source.glob(glob_pattern))
    log.info("Found %d dated snapshots matching %r", len(dated), glob_pattern)

    companies_csv = next(
        (p for p in (source / "companies.csv", source / "companies" / "all.csv") if p.exists()),
        None,
    )
    log.info("Companies CSV: %s", companies_csv or "(none)")

    if args.dry_run:
        log.info("Dry run — exiting without uploading")
        return 0

    config = R2Config.from_env()
    log.info("R2 endpoint: %s  bucket: %s", config.endpoint_url, config.bucket)
    if not config.public_base_url:
        log.warning(
            "CLOUDFLARE_PUBLIC_BASE_URL is not set — manifest will reference object "
            "keys instead of public URLs. Set it to your CDN base "
            "(e.g. https://storage.stapply.ai) for the lib to be able to fetch."
        )

    r2 = R2Client(config)
    publisher = DatasetPublisher(r2, write_parquet=not args.no_parquet)

    result = publisher.publish_from_directory(
        source_dir=source,
        ats_csv_pattern="{ats}/jobs.csv",
        dated_snapshots=dated,
        companies_csv=companies_csv,
    )

    log.info("=" * 70)
    log.info("Published: %s jobs across %s companies", f"{result.total_jobs:,}", f"{result.total_companies:,}")
    log.info("Manifest:  %s", result.manifest_key)
    log.info("Files:     %d", len(result.files))
    log.info("Duration:  %.1fs", result.duration_seconds)
    if config.public_base_url:
        log.info("Manifest URL: %s/%s", config.public_base_url.rstrip("/"), result.manifest_key)

    if args.prune_old_dated:
        from datetime import date

        keep = date.today().isoformat()
        log.info("Pruning dated snapshots in R2 (keeping only %s)...", keep)
        deleted = publisher.prune_old_dated_snapshots(keep_date=keep)
        log.info("Deleted %d obsolete dated objects", deleted)

    log.info("=" * 70)
    return 0


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader so we don't require python-dotenv as a dep."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


if __name__ == "__main__":
    raise SystemExit(main())
