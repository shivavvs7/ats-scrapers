import csv
import json
import sys
from pathlib import Path

from pydantic import ValidationError

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from export_utils import generate_job_id, write_jobs_csv
from models.join import JoinCompanyData


def build_job_url(company_slug: str, job_id_param: str) -> str:
    """Build the job URL from company slug and job ID param."""
    if not job_id_param:
        return ""
    return f"https://join.com/companies/{company_slug}/{job_id_param}"


def main():
    companies_dir = Path(__file__).resolve().parent / "companies"
    jobs_csv_path = Path(__file__).resolve().parent / "jobs.csv"
    companies_csv_path = Path(__file__).resolve().parent / "join_companies.csv"

    # Build slug to name mapping from join_companies.csv
    slug_to_name = {}
    if companies_csv_path.exists():
        from urllib.parse import urlparse

        with open(companies_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                parsed = urlparse(row["url"])
                path_parts = parsed.path.strip("/").split("/")
                if len(path_parts) >= 2:
                    slug = path_parts[1]
                    slug_to_name[slug] = row["name"]

    job_rows = []

    if not companies_dir.exists() or not companies_dir.is_dir():
        print(f"Companies directory does not exist: {companies_dir}")
        return

    for json_file in sorted(companies_dir.glob("*.json")):
        company_slug = json_file.stem

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Get company name: prefer JSON, fallback to CSV, then slug
            company_name = (
                data.get("name") or slug_to_name.get(company_slug) or company_slug
            )

            parsed = JoinCompanyData(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            print(f"Error parsing {json_file}: {e}")
            continue

        for job in parsed.jobs:
            url = build_job_url(company_slug, job.idParam)
            ats_id = str(job.id)

            job_rows.append(
                {
                    "url": url,
                    "title": job.title or "",
                    "location": job.location,
                    "company": company_name,
                    "ats_id": ats_id,
                    "id": generate_job_id("join", url, ats_id),
                }
            )

    print(f"Processed {len(job_rows)} total jobs")
    write_jobs_csv(jobs_csv_path, job_rows)


if __name__ == "__main__":
    main()
