"""
Export Phenom jobs to CSV format.

Reads JSON files from phenom/companies/ directory and exports to standardized CSV.
"""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from export_utils import generate_job_id, write_jobs_csv  # noqa: E402
from models.phenom import PhenomJob  # noqa: E402


def construct_job_url(base_url: str, job_id: str) -> str:
    """
    Construct job URL from base URL and job ID.

    Phenom job URLs typically follow pattern: {base_url}/job/{jobId}
    However, this may vary by company configuration.

    Args:
        base_url: Company base URL (e.g., "https://jobs.bell.ca")
        job_id: Job ID from API

    Returns:
        Constructed job URL
    """
    # Remove trailing slash from base_url
    base_url = base_url.rstrip("/")
    return f"{base_url}/job/{job_id}"


def main():
    companies_dir = Path(__file__).resolve().parent / "companies"
    jobs_csv_path = Path(__file__).resolve().parent / "jobs.csv"
    companies_csv_path = Path(__file__).resolve().parent / "companies.csv"

    # Build mapping from slug (domain) to company info
    slug_to_info = {}
    if companies_csv_path.exists():
        import csv

        with open(companies_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row["url"]
                # Normalize URL
                if not url.startswith("http"):
                    url = f"https://{url}"

                # Extract domain slug
                from urllib.parse import urlparse
                parsed = urlparse(url)
                domain = parsed.netloc.lower()

                slug_to_info[domain] = {
                    "name": row.get("name", domain),
                    "url": url
                }

    job_rows = []

    if not companies_dir.exists() or not companies_dir.is_dir():
        print(f"Companies directory does not exist: {companies_dir}")
    else:
        for json_file in sorted(companies_dir.glob("*.json")):
            # File name is the domain slug
            domain_slug = json_file.stem

            # Get company info
            company_info = slug_to_info.get(domain_slug, {})
            company_name = company_info.get("name", domain_slug)
            base_url = company_info.get("url", f"https://{domain_slug}")

            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Check if name field exists in JSON (prefer this over CSV)
                if isinstance(data, dict) and "name" in data:
                    company_name = data["name"]

            except json.JSONDecodeError:
                print(f"Warning: Could not parse {json_file}")
                continue

            # Extract jobs list
            job_list = []
            if isinstance(data, list):
                job_list = data
            elif isinstance(data, dict):
                job_list = data.get("jobs", [])

            if not isinstance(job_list, list):
                print(f"Warning: No jobs found in {json_file}")
                continue

            print(f"Processing {len(job_list)} jobs from {domain_slug} ({company_name})")

            for job_data in job_list:
                try:
                    job = PhenomJob(**job_data)
                except ValidationError as e:
                    # Skip invalid jobs but don't crash
                    continue

                # Extract job ID (prefer jobId, fallback to reqId)
                job_id = job.jobId or job.reqId
                if not job_id:
                    # Skip jobs without IDs
                    continue

                # Construct job URL
                url = construct_job_url(base_url, job_id)

                # Extract title
                title = job.title or ""

                # Extract location
                # Phenom has multiple location fields, try to build a comprehensive string
                location_parts = []
                if job.city:
                    location_parts.append(job.city)
                if job.state:
                    location_parts.append(job.state)
                if job.country:
                    location_parts.append(job.country)

                # If no structured location, use the location field
                if not location_parts and job.location:
                    location_str = job.location
                elif location_parts:
                    location_str = ", ".join(location_parts)
                else:
                    location_str = ""

                # Use jobId as ats_id
                ats_id = job_id

                job_rows.append(
                    {
                        "url": url,
                        "title": title,
                        "location": location_str,
                        "company": company_name,
                        "ats_id": ats_id,
                        "id": generate_job_id("phenom", url, ats_id),
                    }
                )

    print(f"Processed {len(job_rows)} total jobs")
    write_jobs_csv(jobs_csv_path, job_rows)


if __name__ == "__main__":
    main()
