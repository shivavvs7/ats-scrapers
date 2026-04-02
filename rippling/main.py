"""Utility script to fetch Rippling company job data from the API."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

sys.path.append(str(Path(__file__).parent.parent))
from models.rippling import RipplingJob, RipplingJobBoard, RipplingCompanyData


REPO_DIR = Path(__file__).resolve().parent
DEFAULT_COMPANIES_CSV = REPO_DIR / "rippling_companies.csv"
COMPANIES_DIR = REPO_DIR / "companies"
COMPANIES_DIR.mkdir(exist_ok=True)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


def fetch_company_jobs_api(slug: str, timeout: int = 30) -> Optional[list[dict]]:
    """Fetch jobs for a company using the Rippling API."""
    api_url = f"https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs"
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        session = requests.Session()
        response = session.get(api_url, headers=headers, timeout=timeout)
        
        # Handle 404 - return None to indicate company not found
        if response.status_code == 404:
            return None
        
        response.raise_for_status()
        jobs = response.json()
        
        # Transform API response to match RipplingJob model structure
        transformed_jobs = []
        for job in jobs:
            transformed_job = job.copy()
            
            # Convert workLocation object to workLocations list
            if "workLocation" in transformed_job:
                work_location = transformed_job.pop("workLocation")
                if isinstance(work_location, dict) and "label" in work_location:
                    transformed_job["workLocations"] = [work_location["label"]]
                else:
                    transformed_job["workLocations"] = []
            
            # Ensure uuid is also set as id for compatibility
            if "uuid" in transformed_job and "id" not in transformed_job:
                transformed_job["id"] = transformed_job["uuid"]
            
            # Ensure name is also set as title for compatibility
            if "name" in transformed_job and "title" not in transformed_job:
                transformed_job["title"] = transformed_job["name"]
            
            transformed_jobs.append(transformed_job)
        
        return transformed_jobs
    except requests.exceptions.RequestException as e:
        print(f"  Error fetching API for {slug}: {e}")
        return None


def extract_company_slug(url: str) -> str:
    """Extract company slug from Rippling job board URL."""
    parsed = urlparse(url)
    # Extract slug from path like /company-slug/jobs
    path_parts = [p for p in parsed.path.split("/") if p]
    if path_parts and path_parts[-1] == "jobs":
        return path_parts[-2] if len(path_parts) > 1 else path_parts[0]
    return path_parts[0] if path_parts else "unknown"


def scrape_company_jobs(
    company_url: str, force: bool = False, company_name: str = None
) -> Optional[RipplingCompanyData]:
    """Fetch all jobs for a company using the Rippling API."""
    company_slug = extract_company_slug(company_url)
    file_path = COMPANIES_DIR / f"{company_slug}.json"

    # Check if we should skip scraping
    if not force and file_path.exists():
        try:
            with file_path.open() as f:
                existing_data = json.load(f)
                last_scraped_str = existing_data.get("last_scraped")
                if last_scraped_str:
                    last_scraped = datetime.fromisoformat(last_scraped_str)
                    hours_elapsed = (
                        datetime.now() - last_scraped
                    ).total_seconds() / 3600
                    if hours_elapsed < 12:
                        print(
                            f"Skipping {company_slug} (scraped {hours_elapsed:.1f} hours ago)"
                        )
                        return None
        except Exception:
            pass

    print(f"Fetching jobs for: {company_slug}")
    jobs_data = fetch_company_jobs_api(company_slug)
    if jobs_data is None:
        print(f"  Company '{company_slug}' not found (404), skipping...")
        return None

    if not jobs_data:
        print(f"  No jobs found for {company_slug}")
        return None

    print(f"  Found {len(jobs_data)} job(s)")

    # Build company data object
    # Create a minimal job board object from the slug
    job_board_data = RipplingJobBoard(
        slug=company_slug,
        board_url=f"https://ats.rippling.com/{company_slug}/jobs",
    )

    company_data = RipplingCompanyData(
        company_slug=company_slug,
        name=company_name,
        job_board=job_board_data,
        jobs=[RipplingJob(**job) for job in jobs_data],
        last_scraped=datetime.now().isoformat(),
    )

    # Save to file
    with file_path.open("w") as f:
        json.dump(company_data.model_dump(mode="json", exclude_none=True), f, indent=2)

    print(f"  Saved {len(jobs_data)} jobs to {file_path}")
    return company_data


def read_company_urls(csv_path: Path) -> tuple[list[str], dict[str, str]]:
    """Read company URLs and return a tuple of (urls, slug_to_name mapping)"""
    if not csv_path.exists():
        raise FileNotFoundError(f"Company CSV not found at '{csv_path}'.")

    slug_to_name = {}
    urls = []

    with csv_path.open(encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            url = row.get("url", "")
            name = row.get("name", "")
            if url:
                urls.append(url.strip())
                # Extract slug from URL
                parsed = urlparse(url)
                path_parts = [p for p in parsed.path.split("/") if p]
                if path_parts and path_parts[-1] == "jobs":
                    slug = path_parts[-2] if len(path_parts) > 1 else path_parts[0]
                else:
                    slug = path_parts[0] if path_parts else "unknown"
                if name:
                    slug_to_name[slug] = name

    if not urls:
        raise ValueError(f"No URLs found in '{csv_path}'.")
    return urls, slug_to_name


def run_api_sample(company_url: str, max_jobs: int) -> list[dict]:
    """Sample jobs from API for a company."""
    company_slug = extract_company_slug(company_url)
    print(f"[api-sample] Fetching jobs for {company_slug}")
    jobs_data = fetch_company_jobs_api(company_slug)
    if jobs_data is None:
        print("[api-sample] Company not found (404).")
        return []
    
    if not jobs_data:
        print("[api-sample] No jobs found.")
        return []

    print(f"[api-sample] Found {len(jobs_data)} job(s). Showing up to {max_jobs} entries:")
    for job in jobs_data[:max_jobs]:
        title = job.get("name") or job.get("title") or "<untitled>"
        url = job.get("url") or "<no url>"
        dept = (job.get("department") or {}).get("label") or (job.get("department") or {}).get("name") or "Unknown department"
        work_location = job.get("workLocation", {})
        if isinstance(work_location, dict):
            location = work_location.get("label", "Unknown location")
        else:
            locations = job.get("workLocations", [])
            location = ", ".join(locations) if locations else "Unknown location"
        print(f"  - {title} | {dept} | {location} | {url}")
    return jobs_data[:max_jobs]


def process_companies(
    urls: list[str],
    slug_to_name: dict[str, str],
    max_jobs: int,
    html_sample: bool = False,
    force: bool = False,
) -> None:
    for company_url in urls:
        # Extract slug to get company name
        parsed = urlparse(company_url)
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts and path_parts[-1] == "jobs":
            slug = path_parts[-2] if len(path_parts) > 1 else path_parts[0]
        else:
            slug = path_parts[0] if path_parts else "unknown"
        company_name = slug_to_name.get(slug)

        if html_sample:
            run_api_sample(company_url, max_jobs)
        else:
            scrape_company_jobs(company_url, force=force, company_name=company_name)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Rippling job data directly from the job board HTML."
    )
    parser.add_argument(
        "--csv",
        default=os.environ.get("RIPPLING_COMPANIES_CSV", str(DEFAULT_COMPANIES_CSV)),
        help="Path to rippling_companies.csv.",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("RIPPLING_URL"),
        help="Process only this company URL (otherwise processes all companies from CSV).",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=int(os.environ.get("RIPPLING_MAX_JOBS", 5)),
        help="Max job listings to print per company.",
    )
    parser.add_argument(
        "--html-sample",
        action="store_true",
        help="Show job summaries only (no detailed scraping).",
        dest="html_sample",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-scraping even if data was recently scraped.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()

    if args.url:
        if args.html_sample:
            run_api_sample(args.url, args.max_jobs)
        else:
            scrape_company_jobs(args.url, force=args.force)
        return

    urls, slug_to_name = read_company_urls(Path(args.csv))

    if args.html_sample:
        run_api_sample(urls[0], args.max_jobs)
        return

    process_companies(
        urls,
        slug_to_name,
        args.max_jobs,
        html_sample=args.html_sample,
        force=args.force,
    )


if __name__ == "__main__":
    main()
