"""
Export Oracle HCM Cloud jobs to CSV format.

Reads JSON files from oracle/companies/ and exports to oracle/jobs.csv
with standardized fields: url, title, location, company, ats_id, id
"""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from export_utils import generate_job_id, write_jobs_csv  # noqa: E402
from models.oracle import OracleJob  # noqa: E402


def main():
    companies_dir = Path(__file__).resolve().parent / "companies"
    jobs_csv_path = Path(__file__).resolve().parent / "jobs.csv"
    companies_csv_path = Path(__file__).resolve().parent / "oracle_companies.csv"

    # Build mapping from slug to company name
    slug_to_name = {}
    if companies_csv_path.exists():
        import csv
        from urllib.parse import urlparse

        with open(companies_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row["url"].lower().strip().rstrip("/")
                company_name = row["name"]

                # Parse URL to extract slug (subdomain-region)
                parsed = urlparse(url)
                netloc = parsed.netloc.lower()
                if ".fa." in netloc and ".oraclecloud.com" in netloc:
                    parts = netloc.split(".fa.")
                    subdomain = parts[0]
                    region = parts[1].replace(".oraclecloud.com", "")
                    slug = f"{subdomain}-{region}"
                    slug_to_name[slug] = company_name

    job_rows = []

    if not companies_dir.exists() or not companies_dir.is_dir():
        print(f"Companies directory does not exist: {companies_dir}")
    else:
        for json_file in sorted(companies_dir.glob("*.json")):
            company_slug = json_file.stem
            company_name = company_slug  # fallback

            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Check if name field exists in JSON
                if isinstance(data, dict) and "name" in data:
                    company_name = data["name"]
                else:
                    # Try to find in slug mapping
                    if company_slug in slug_to_name:
                        company_name = slug_to_name[company_slug]

            except json.JSONDecodeError:
                print(f"Failed to parse JSON: {json_file}")
                continue

            # Extract jobs list from data
            job_list = []
            if isinstance(data, dict):
                job_list = data.get("jobs", [])
            elif isinstance(data, list):
                job_list = data

            if not isinstance(job_list, list):
                continue

            # Get config to construct URLs if needed
            config = data.get("config", {}) if isinstance(data, dict) else {}
            subdomain = config.get("subdomain", "")
            region = config.get("region", "")
            site_number = config.get("site_number", "CX_45001")

            for job_data in job_list:
                try:
                    job = OracleJob(**job_data)
                except ValidationError as e:
                    # Skip invalid jobs
                    print(f"Validation error for job in {company_slug}: {e}")
                    continue

                # Extract URL (prefer JobURL, fallback to ExternalApplyURL, or construct it)
                url = job.JobURL or job.ExternalApplyURL
                if not url and subdomain and region and job.Id:
                    # Construct URL using Oracle's standard pattern
                    url = f"https://{subdomain}.fa.{region}.oraclecloud.com/hcmUI/CandidateExperience/en/sites/{site_number}/job/{job.Id}"
                else:
                    url = url or ""

                # Extract ATS ID (prefer Id, fallback to RequisitionNumber)
                ats_id = str(job.Id) if job.Id else job.RequisitionNumber or ""

                # Extract title
                title = job.Title or ""

                # Extract location
                location_parts = []
                if job.PrimaryLocation:
                    location_parts.append(job.PrimaryLocation)
                elif job.WorkLocation:
                    # Build location from WorkLocation object
                    loc_parts = []
                    if job.WorkLocation.City:
                        loc_parts.append(job.WorkLocation.City)
                    if job.WorkLocation.State:
                        loc_parts.append(job.WorkLocation.State)
                    if job.WorkLocation.Country:
                        loc_parts.append(job.WorkLocation.Country)
                    if loc_parts:
                        location_parts.append(", ".join(loc_parts))
                elif job.Country:
                    location_parts.append(job.Country)

                # Add other work locations if available
                if job.otherWorkLocations:
                    for other_loc in job.otherWorkLocations:
                        if hasattr(other_loc, 'LocationName') and other_loc.LocationName:
                            location_parts.append(other_loc.LocationName)
                        elif hasattr(other_loc, 'City') and other_loc.City:
                            loc_parts = []
                            if other_loc.City:
                                loc_parts.append(other_loc.City)
                            if hasattr(other_loc, 'State') and other_loc.State:
                                loc_parts.append(other_loc.State)
                            if hasattr(other_loc, 'Country') and other_loc.Country:
                                loc_parts.append(other_loc.Country)
                            if loc_parts:
                                location_parts.append(", ".join(loc_parts))

                location_str = "; ".join(location_parts) if location_parts else ""

                job_rows.append(
                    {
                        "url": url,
                        "title": title,
                        "location": location_str,
                        "company": company_name,
                        "ats_id": ats_id,
                        "id": generate_job_id("oracle", url, ats_id),
                    }
                )

    print(f"Processed {len(job_rows)} total jobs")
    write_jobs_csv(jobs_csv_path, job_rows)


if __name__ == "__main__":
    main()
