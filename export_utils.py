from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List
from uuid import NAMESPACE_URL, uuid5


FIELDNAMES = ["url", "title", "location", "company", "ats_id", "id"]


def generate_job_id(platform: str, url: str | None, ats_id: str | None) -> str:
    """
    Generate a deterministic UUID for a job using the platform, ats_id, and URL.
    Falls back gracefully when values are missing so the ID stays stable
    between runs.
    """
    platform = platform or "unknown"
    url = url or ""
    ats_id = ats_id or ""
    unique_key = f"{platform}:{ats_id}:{url}"
    return str(uuid5(NAMESPACE_URL, unique_key))



def write_jobs_csv(jobs_csv_path: Path, rows: List[Dict[str, str]]) -> None:
    """
    Write the jobs CSV with all current jobs.
    """
    jobs_csv_path = Path(jobs_csv_path)
    jobs_csv_path.parent.mkdir(parents=True, exist_ok=True)

    with open(jobs_csv_path, "w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
