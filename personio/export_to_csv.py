import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from pydantic import ValidationError

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from export_utils import generate_job_id, write_jobs_csv
from models.personio import PersonioJob


def build_job_url(subdomain: str, job_slug: str) -> str:
    """Build the job URL from company subdomain and job slug."""
    if not job_slug:
        return f"https://{subdomain}.jobs.personio.com"
    return f"https://{subdomain}.jobs.personio.com/job/{job_slug}"


def extract_subdomain_from_filename(filename: str) -> str:
    """Extract the Personio subdomain from the JSON filename."""
    # Filenames are like "company-name.json"
    return filename.replace(".json", "")


def main():
    companies_dir = Path(__file__).resolve().parent / "companies"
    jobs_csv_path = Path(__file__).resolve().parent / "jobs.csv"
    companies_csv_path = Path(__file__).resolve().parent / "personio_companies.csv"

    # Build mapping from subdomain to company name
    subdomain_to_name = {}
    if companies_csv_path.exists():
        with open(companies_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row["url"]
                # Extract subdomain from URL like https://company.jobs.personio.com
                parsed = urlparse(url)
                hostname = parsed.hostname or ""
                if ".jobs.personio." in hostname:
                    subdomain = hostname.split(".")[0]
                    subdomain_to_name[subdomain] = row["name"]

    job_rows = []

    if not companies_dir.exists() or not companies_dir.is_dir():
        print(f"Companies directory does not exist: {companies_dir}")
        return

    for json_file in sorted(companies_dir.glob("*.json")):
        subdomain = extract_subdomain_from_filename(json_file.name)

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Get company name: prefer JSON, fallback to CSV mapping, then subdomain
            company_name = data.get("name") or subdomain_to_name.get(subdomain) or subdomain

            # Jobs are in a list directly or under "jobs" key
            jobs_data = data.get("jobs", []) if isinstance(data, dict) else data
            if not isinstance(jobs_data, list):
                continue

            for job_data in jobs_data:
                try:
                    job = PersonioJob(**job_data)
                except ValidationError as e:
                    print(f"Validation error for job in {subdomain}: {e}")
                    continue

                # Build job URL
                url = build_job_url(subdomain, job.slug)
                ats_id = str(job.id)

                # Build location string from offices
                location_parts = []
                if job.office:
                    location_parts.append(job.office)
                if job.all_offices:
                    for office in job.all_offices:
                        if office and office not in location_parts:
                            location_parts.append(office)
                location = "; ".join(location_parts) if location_parts else ""

                job_rows.append(
                    {
                        "url": url,
                        "title": job.name or "",
                        "location": location,
                        "company": company_name,
                        "ats_id": ats_id,
                        "id": generate_job_id("personio", url, ats_id),
                    }
                )

        except (json.JSONDecodeError, OSError) as e:
            print(f"Error reading {json_file}: {e}")
            continue

    print(f"Processed {len(job_rows)} total jobs")
    write_jobs_csv(jobs_csv_path, job_rows)


if __name__ == "__main__":
    main()
