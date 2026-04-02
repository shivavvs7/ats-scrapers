import json
import sys
from pathlib import Path

from pydantic import ValidationError

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from export_utils import generate_job_id, write_jobs_csv  # noqa: E402
from models.smartrecruiters import SmartRecruitersApiResponse  # noqa: E402


def format_location(location_obj) -> str:
    """Format location object into a string"""
    if not location_obj:
        return ""
    
    parts = []
    if location_obj.city:
        parts.append(location_obj.city)
    if location_obj.region:
        parts.append(location_obj.region)
    if location_obj.country:
        parts.append(location_obj.country)
    
    location_str = ", ".join(parts)
    
    # Add remote indicator if applicable
    if location_obj.remote:
        if location_str:
            location_str += " (Remote)"
        else:
            location_str = "Remote"
    
    return location_str


def main():
    companies_dir = Path(__file__).resolve().parent / "companies"
    jobs_csv_path = Path(__file__).resolve().parent / "jobs.csv"
    companies_csv_path = Path(__file__).resolve().parent / "smartrecruiters_companies.csv"

    # Build mapping from slug to company name
    slug_to_name = {}
    if companies_csv_path.exists():
        import csv
        from urllib.parse import urlparse, unquote

        with open(companies_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row["url"]
                # Extract slug from URL and URL-decode it
                parsed = urlparse(url)
                slug = parsed.path.lstrip("/")
                # URL-decode the slug for matching
                decoded_slug = unquote(slug)
                # Store both encoded and decoded versions (and lowercase versions) for lookup
                slug_to_name[slug] = row["name"]
                slug_to_name[slug.lower()] = row["name"]
                slug_to_name[decoded_slug] = row["name"]
                slug_to_name[decoded_slug.lower()] = row["name"]

    job_rows = []

    if not companies_dir.exists() or not companies_dir.is_dir():
        print(f"Companies directory does not exist: {companies_dir}")
    else:
        for json_file in sorted(companies_dir.glob("*.json")):
            company_slug = json_file.stem
            # Normalize slug to lowercase for lookup (URLs are case-insensitive)
            company_slug_lower = company_slug.lower()
            # Try to get company name from JSON first, then from CSV mapping
            company_name = company_slug  # fallback
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Check if name field exists in JSON
                if "name" in data:
                    # Ensure name is not URL-encoded (shouldn't happen, but safety check)
                    from urllib.parse import unquote

                    company_name = data["name"]
                    # If name looks URL-encoded, prefer CSV name instead
                    if "%" in company_name:
                        decoded_slug = unquote(company_slug_lower)
                        if company_slug_lower in slug_to_name:
                            company_name = slug_to_name[company_slug_lower]
                        elif decoded_slug in slug_to_name:
                            company_name = slug_to_name[decoded_slug]
                else:
                    # Try to find in slug mapping (try both encoded and decoded versions, case-insensitive)
                    from urllib.parse import unquote

                    decoded_slug = unquote(company_slug_lower)
                    if company_slug_lower in slug_to_name:
                        company_name = slug_to_name[company_slug_lower]
                    elif decoded_slug in slug_to_name:
                        company_name = slug_to_name[decoded_slug]
                parsed = SmartRecruitersApiResponse(**data)
            except (json.JSONDecodeError, ValidationError):
                continue

            for posting in parsed.content:
                url = posting.job_url or posting.applyUrl or ""
                ats_id = posting.id or posting.uuid or ""
                title = posting.name or ""
                location = format_location(posting.location)
                
                job_rows.append(
                    {
                        "url": url,
                        "title": title,
                        "location": location,
                        "company": company_name,
                        "ats_id": ats_id or "",
                        "id": generate_job_id("smartrecruiters", url, ats_id),
                    }
                )

    print(f"Processed {len(job_rows)} total jobs")
    write_jobs_csv(jobs_csv_path, job_rows)


if __name__ == "__main__":
    main()
