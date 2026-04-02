"""Export Avature job data to CSV using shared utilities."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from export_utils import generate_job_id, write_jobs_csv  # noqa: E402


def extract_company_name_from_filename(filename: str) -> str:
    """Extract company name from JSON filename."""
    # Remove .json extension
    name = filename.replace(".json", "")
    # Replace underscores with spaces
    name = name.replace("_", " ")
    # Try to extract just the domain part
    if "_" in name:
        parts = name.split("_")
        # Look for the main domain part (usually first or second)
        for part in parts:
            if part and part not in ["https:", "http:", "", "careers", "jobs"]:
                return part.replace("-", " ").title()
    return name.replace("-", " ").title()


def main() -> None:
    avature_dir = Path(__file__).resolve().parent
    companies_dir = avature_dir / "companies"
    jobs_csv_path = avature_dir / "jobs.csv"
    companies_csv_path = avature_dir / "companies.csv"

    # Build mapping from URL pattern to company name
    url_to_name = {}
    if companies_csv_path.exists():
        with open(companies_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get("url", "").strip()
                name = row.get("name", "").strip()
                if url and name and name != "TBD":
                    # Store partial URL match
                    url_to_name[url] = name

    job_rows = []

    if not companies_dir.exists() or not companies_dir.is_dir():
        print(f"Companies directory does not exist: {companies_dir}")
        return

    for json_file in sorted(companies_dir.glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error reading {json_file}: {e}")
            continue

        # Get company name: prefer JSON, fallback to filename-based
        company_name = data.get("name")
        if not company_name:
            # Try to match with CSV
            file_stem = json_file.stem
            for url, name in url_to_name.items():
                safe_url = url.replace("https://", "").replace("http://", "").replace("/", "_")
                if safe_url in file_stem or file_stem in safe_url:
                    company_name = name
                    break
        
        if not company_name:
            company_name = extract_company_name_from_filename(json_file.name)

        jobs = data.get("jobs", [])
        if not isinstance(jobs, list):
            continue

        for job_data in jobs:
            if not isinstance(job_data, dict):
                continue

            url = job_data.get("url", "").strip()
            title = job_data.get("title", "").strip()
            location = job_data.get("location", "").strip()
            ats_id = job_data.get("job_id", "").strip()

            job_rows.append(
                {
                    "url": url,
                    "title": title,
                    "location": location,
                    "company": company_name,
                    "ats_id": ats_id,
                    "id": generate_job_id("avature", url, ats_id),
                }
            )

    print(f"Processed {len(job_rows)} total jobs")
    write_jobs_csv(jobs_csv_path, job_rows)


if __name__ == "__main__":
    main()
