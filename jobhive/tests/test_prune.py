"""Tests for `DatasetPublisher.prune_old_dated_snapshots` and the underlying
R2Client.delete_many helper.
"""

from __future__ import annotations

import pandas as pd

from jobhive.storage.publisher import DatasetPublisher


def _seed_dated_snapshots(publisher: DatasetPublisher, dates: list[str]) -> None:
    """Pre-populate the fake R2 with dated snapshots in CSV+parquet form."""
    fake = publisher._r2
    for d in dates:
        for ext in ("csv", "parquet"):
            fake.upload_bytes(
                b"data",
                f"jobhive/v1/jobs/by-date/{d}.{ext}",
                content_type="application/octet-stream",
            )


def test_prune_keeps_target_date_and_deletes_rest(fake_r2) -> None:
    publisher = DatasetPublisher(fake_r2, write_parquet=False)
    _seed_dated_snapshots(
        publisher,
        ["2026-04-01", "2026-04-15", "2026-05-03", "2026-04-30"],
    )

    deleted = publisher.prune_old_dated_snapshots(keep_date="2026-05-03")

    assert deleted == 6  # 3 dates x 2 formats
    remaining = sorted(k for k in fake_r2.uploads if "by-date/" in k)
    assert remaining == [
        "jobhive/v1/jobs/by-date/2026-05-03.csv",
        "jobhive/v1/jobs/by-date/2026-05-03.parquet",
    ]


def test_prune_is_idempotent(fake_r2) -> None:
    publisher = DatasetPublisher(fake_r2, write_parquet=False)
    _seed_dated_snapshots(publisher, ["2026-05-03"])
    assert publisher.prune_old_dated_snapshots(keep_date="2026-05-03") == 0
    assert publisher.prune_old_dated_snapshots(keep_date="2026-05-03") == 0


def test_prune_returns_zero_when_nothing_present(fake_r2) -> None:
    publisher = DatasetPublisher(fake_r2, write_parquet=False)
    assert publisher.prune_old_dated_snapshots(keep_date="2026-05-03") == 0


def test_prune_does_not_touch_non_dated_objects(fake_r2) -> None:
    publisher = DatasetPublisher(fake_r2, write_parquet=False)
    _seed_dated_snapshots(publisher, ["2026-04-01"])
    fake_r2.upload_bytes(b"x", "jobhive/v1/jobs/all.csv")
    fake_r2.upload_bytes(b"x", "jobhive/v1/jobs/by-ats/greenhouse.csv")
    fake_r2.upload_bytes(b"x", "jobhive/v1/manifest.json")

    publisher.prune_old_dated_snapshots(keep_date="2026-05-03")

    assert "jobhive/v1/jobs/all.csv" in fake_r2.uploads
    assert "jobhive/v1/jobs/by-ats/greenhouse.csv" in fake_r2.uploads
    assert "jobhive/v1/manifest.json" in fake_r2.uploads


def test_prune_after_publish_full_flow(ats_csv_dir, fake_r2, tmp_path) -> None:
    snap_old = tmp_path / "ai-01-04-2026.csv"
    snap_today = tmp_path / "ai-03-05-2026.csv"
    pd.DataFrame(
        [{"url": "https://x/1", "title": "x", "company": "c", "ats_type": "ashby"}]
    ).to_csv(snap_old, index=False)
    pd.DataFrame(
        [{"url": "https://x/2", "title": "y", "company": "c", "ats_type": "ashby"}]
    ).to_csv(snap_today, index=False)

    publisher = DatasetPublisher(fake_r2, write_parquet=True)
    publisher.publish_from_directory(
        ats_csv_dir, dated_snapshots=[snap_old, snap_today]
    )
    deleted = publisher.prune_old_dated_snapshots(keep_date="2026-05-03")

    # by-date is parquet-only, so the old snapshot's parquet should be deleted
    assert deleted == 1
    assert "jobhive/v1/jobs/by-date/2026-05-03.parquet" in fake_r2.uploads
    assert "jobhive/v1/jobs/by-date/2026-04-01.parquet" not in fake_r2.uploads
