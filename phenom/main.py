"""
Phenom People ATS Job Scraper

Scrapes job listings from Phenom-powered career sites using the existing
PhenomJobsClient API client.

Phenom companies use custom branded domains with no standard URL pattern:
- Bell Canada: https://jobs.bell.ca
- GE Healthcare: https://careers.gehealthcare.com
- Each company requires company_code, locale, and country configuration

URL Slug: Domain name (e.g., jobs.bell.ca, careers.gehealthcare.com)

Usage:
    python phenom/main.py [--force] [url]

    # Scrape all companies from phenom/companies.csv
    python phenom/main.py

    # Force re-scrape all companies (ignore 12-hour cache)
    python phenom/main.py --force

    # Scrape a single company (must exist in CSV with config)
    python phenom/main.py https://jobs.bell.ca
"""

import asyncio
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phenom.phenom_jobs_api.api_client import PhenomJobsClient  # noqa: E402

# Configuration constants
MAX_RETRIES = 3
BASE_RETRY_DELAY = 2  # seconds
MIN_SCRAPE_DELAY = 1  # seconds
MAX_SCRAPE_DELAY = 3  # seconds
REQUEST_TIMEOUT = 30  # seconds
CACHE_HOURS = 12  # Re-scrape after 12 hours


def extract_domain_slug(url: str) -> str:
    """
    Extract domain as slug from Phenom URL.

    Since Phenom uses custom branded domains, the domain itself is the identifier.

    Args:
        url: Phenom careers URL (e.g., "https://jobs.bell.ca")

    Returns:
        Domain slug (e.g., "jobs.bell.ca")
    """
    parsed = urlparse(url)
    return parsed.netloc.lower()


def load_company_data(file_path: str) -> dict | None:
    """Load company data from JSON file"""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def should_scrape_company(
    company_data: dict | None, force: bool = False
) -> tuple[bool, float | None]:
    """
    Determine if we should scrape a company based on last_scraped timestamp.
    Returns (should_scrape, hours_since_last_scrape)
    """
    if force:
        return True, None

    if company_data is None:
        return True, None

    if isinstance(company_data, dict):
        last_scraped_str = company_data.get("last_scraped")
        if not last_scraped_str:
            return True, None

        try:
            last_scraped = datetime.fromisoformat(last_scraped_str)
            hours_elapsed = (datetime.now() - last_scraped).total_seconds() / 3600

            # Scrape if more than 12 hours old
            should_scrape = hours_elapsed >= CACHE_HOURS
            return should_scrape, hours_elapsed
        except (ValueError, TypeError):
            return True, None

    return True, None


def save_company_data(
    file_path: str,
    jobs: list,
    company_name: str = None,
    config: dict = None
) -> None:
    """Save company data with last_scraped timestamp and metadata"""
    wrapped_data = {
        "last_scraped": datetime.now().isoformat(),
        "jobs": jobs,
    }

    if company_name:
        wrapped_data["name"] = company_name

    if config:
        wrapped_data["config"] = config

    with open(file_path, "w") as f:
        json.dump(wrapped_data, f, indent=2)


async def scrape_phenom_jobs(
    url: str,
    force: bool = False,
    company_name: str = None,
    company_code: str = None,
    locale: str = "en",
    country: str = "us"
) -> tuple[list | None, int, bool]:
    """
    Scrape jobs from a single Phenom company.

    Args:
        url: Base URL (e.g., "https://jobs.bell.ca")
        force: Force re-scrape (ignore 12-hour cache)
        company_name: Company name for metadata
        company_code: Phenom company code (e.g., "BECACA")
        locale: Locale code (e.g., "en_ca")
        country: Country code (e.g., "ca")

    Returns:
        Tuple of (jobs_list, num_jobs, was_scraped)
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    companies_dir = os.path.join(script_dir, "companies")

    if not os.path.exists(companies_dir):
        os.makedirs(companies_dir)

    # Extract domain slug
    slug = extract_domain_slug(url)
    file_path = os.path.join(companies_dir, f"{slug}.json")

    # Check if we should scrape this company
    company_data = load_company_data(file_path)
    should_scrape, hours_elapsed = should_scrape_company(company_data, force)

    if not should_scrape:
        print(
            f"Scraped {slug} {hours_elapsed:.1f} hours ago. I will not scrape again."
        )
        jobs = company_data.get("jobs", []) if isinstance(company_data, dict) else []
        num_jobs = len(jobs)
        return jobs, num_jobs, False

    # Log decision to scrape
    if force:
        print(f"Forcing scrape for '{slug}' (force=True).")
    elif hours_elapsed is not None:
        print(
            f"Scraped {slug} {hours_elapsed:.1f} hours ago. I will scrape again."
        )
    elif company_data is None:
        print(f"Company '{slug}' data file does not exist. I will scrape.")
    elif isinstance(company_data, dict) and not company_data.get("last_scraped"):
        print(f"Company '{slug}' has no last_scraped field. I will scrape.")
    else:
        print(f"Company '{slug}' last_scraped field is invalid. I will scrape.")

    # Validate required config
    if not company_code:
        print(f"Error: company_code is required for {slug}")
        return None, 0, False

    # Initialize Phenom API client
    print(f"Initializing Phenom client for {slug}...")
    print(f"  URL: {url}")
    print(f"  Company Code: {company_code}")
    print(f"  Locale: {locale}")
    print(f"  Country: {country}")

    try:
        client = PhenomJobsClient(
            base_url=url,
            company_code=company_code,
            locale=locale,
            country=country
        )

        # Use get_all_jobs() for automatic pagination
        print(f"Fetching all jobs from {slug}...")
        all_jobs = client.get_all_jobs()

        if not all_jobs:
            print(f"No jobs found for {slug}")
            return [], 0, True

        # Save with metadata
        config = {
            "company_code": company_code,
            "locale": locale,
            "country": country
        }
        save_company_data(file_path, all_jobs, company_name, config)

        num_jobs = len(all_jobs)
        print(f"Successfully scraped {num_jobs} jobs from {slug}")
        return all_jobs, num_jobs, True

    except Exception as e:
        print(f"Error scraping {slug}: {e}")
        return None, 0, False


async def scrape_all_phenom_jobs(force: bool = False):
    """Scrape all companies from phenom/companies.csv"""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "companies.csv")

    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return

    count = 0
    successful_companies = 0
    failed_companies = 0
    skipped_companies = 0

    # Read company configurations from CSV
    companies = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Ensure URL has protocol
            url = row["url"]
            if not url.startswith("http"):
                url = f"https://{url}"

            companies.append({
                "url": url,
                "name": row.get("name", ""),
                "company_code": row.get("company_code", ""),
                "locale": row.get("locale", "en"),
                "country": row.get("country", "us")
            })

    print(f"Processing {len(companies)} companies...")

    for company_info in companies:
        slug = extract_domain_slug(company_info["url"])
        print(f"\nProcessing company: {slug}")

        # Validate required fields
        if not company_info["company_code"]:
            print(f"Error: Missing company_code for {slug}. Skipping.")
            failed_companies += 1
            continue

        data, num_jobs, was_scraped = await scrape_phenom_jobs(
            url=company_info["url"],
            force=force,
            company_name=company_info["name"],
            company_code=company_info["company_code"],
            locale=company_info["locale"],
            country=company_info["country"]
        )

        if data is not None:
            count += num_jobs
            if was_scraped:
                successful_companies += 1
                # Add delay between scrapes to be respectful
                await asyncio.sleep(MIN_SCRAPE_DELAY)
            else:
                skipped_companies += 1
        else:
            failed_companies += 1
            print(f"Failed to scrape {slug}")

    print(
        f"\nDone! Processed {count} total jobs from {successful_companies} companies "
        f"({skipped_companies} skipped, {failed_companies} failed)"
    )
    return script_dir


async def scrape_single_company(url: str, force: bool = False):
    """
    Scrape a single company by URL.
    Looks up config from CSV file.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "companies.csv")

    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        print("Cannot look up company configuration.")
        return

    # Normalize URL
    if not url.startswith("http"):
        url = f"https://{url}"

    slug = extract_domain_slug(url)

    # Find company config in CSV
    company_info = None
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_url = row["url"]
            if not row_url.startswith("http"):
                row_url = f"https://{row_url}"

            if extract_domain_slug(row_url) == slug:
                company_info = {
                    "name": row.get("name", ""),
                    "company_code": row.get("company_code", ""),
                    "locale": row.get("locale", "en"),
                    "country": row.get("country", "us")
                }
                break

    if not company_info:
        print(f"Error: Company {slug} not found in {csv_path}")
        print("Please add the company with proper configuration first.")
        return

    if not company_info["company_code"]:
        print(f"Error: Missing company_code for {slug} in CSV")
        return

    # Scrape the company
    data, num_jobs, was_scraped = await scrape_phenom_jobs(
        url=url,
        force=force,
        company_name=company_info["name"],
        company_code=company_info["company_code"],
        locale=company_info["locale"],
        country=company_info["country"]
    )

    if data is not None:
        if was_scraped:
            print(f"\nSuccessfully scraped {num_jobs} jobs from {slug}")
        else:
            print(f"\nSkipped scraping {slug} ({num_jobs} jobs in cache)")
    else:
        print(f"\nFailed to scrape {slug}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phenom People job scraper")
    parser.add_argument(
        "--force", action="store_true", help="Force re-scrape (ignore 12-hour cache)"
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="Company URL to scrape (optional, scrapes all if not provided)",
    )
    args = parser.parse_args()

    start_time = time.perf_counter()
    try:
        if args.url:
            asyncio.run(scrape_single_company(args.url, args.force))
        else:
            asyncio.run(scrape_all_phenom_jobs(args.force))
    finally:
        elapsed = time.perf_counter() - start_time
        print(f"Total runtime: {elapsed:.2f} seconds")
