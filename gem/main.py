#!/usr/bin/env python3
"""Gem ATS Job Scraper"""
import asyncio
import argparse
import csv
import json
import os
import random
import time
from datetime import datetime
from urllib.parse import urlparse
import sys

# Add the scripts directory to the path to import api_client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts', 'gem_jobs_scraper'))
from api_client import GemATSScraper

MAX_RETRIES = 3
BASE_RETRY_DELAY = 2  # seconds
MIN_SCRAPE_DELAY = 1  # seconds
MAX_SCRAPE_DELAY = 3  # seconds
REQUEST_TIMEOUT = 30  # seconds


def extract_company_id(url: str) -> str:
    """Extract company ID from Gem job board URL"""
    parsed = urlparse(url)
    # Extract the path and remove leading slash
    path = parsed.path.lstrip("/")
    return path


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
            should_scrape = hours_elapsed >= 12
            return should_scrape, hours_elapsed
        except (ValueError, TypeError):
            return True, None

    return True, None


def save_company_data(file_path: str, job_postings: list, company_name: str = None) -> None:
    """Save company data with last_scraped timestamp and company name"""
    wrapped_data = {
        "last_scraped": datetime.now().isoformat(),
        "jobs": job_postings
    }
    if company_name:
        wrapped_data["name"] = company_name
    with open(file_path, "w") as f:
        json.dump(wrapped_data, f, indent=2)


async def scrape_gem_jobs(
    company_id: str, force: bool = False, company_name: str = None
):
    """Scrape jobs for a single company"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    companies_dir = os.path.join(script_dir, "companies")

    if not os.path.exists(companies_dir):
        os.makedirs(companies_dir)

    file_path = os.path.join(companies_dir, f"{company_id}.json")

    # Check if we should scrape this company
    company_data = load_company_data(file_path)
    should_scrape, hours_elapsed = should_scrape_company(company_data, force)

    if not should_scrape:
        print(
            f"Scraped {company_id} {hours_elapsed:.1f} hours ago. I will not scrape again."
        )
        # Return existing data info with skipped flag
        if isinstance(company_data, dict):
            jobs = company_data.get("jobs", [])
        else:
            jobs = company_data if isinstance(company_data, list) else []
        num_jobs = len(jobs)
        return (
            jobs,
            num_jobs,
            False,
        )  # False = not scraped (skipped)

    # Log decision to scrape
    if force:
        print(f"Forcing scrape for '{company_id}' (force=True).")
    elif hours_elapsed is not None:
        print(
            f"Scraped {company_id} {hours_elapsed:.1f} hours ago. I will scrape again."
        )
    elif company_data is None:
        print(f"Company '{company_id}' data file does not exist. I will scrape.")
    elif isinstance(company_data, dict) and not company_data.get("last_scraped"):
        print(f"Company '{company_id}' has no last_scraped field. I will scrape.")
    else:
        print(f"Company '{company_id}' last_scraped field is invalid. I will scrape.")

    print(f"Fetching jobs for {company_id}...")

    scraper = GemATSScraper()

    attempt = 1
    while attempt <= MAX_RETRIES:
        try:
            # Get jobs data from API client
            result = scraper.get_jobs(company_id)

            # Extract only the job postings (not filters or other fields)
            job_postings = result.get('job_postings', [])

            # Save with last_scraped timestamp and company name
            save_company_data(file_path, job_postings, company_name)

            scraper.close()
            return job_postings, len(job_postings), True  # True = scraped

        except Exception as err:
            if attempt == MAX_RETRIES:
                print(
                    f"Exceeded retries for '{company_id}' due to error: {err}"
                )
                scraper.close()
                return None, 0, False
            delay = BASE_RETRY_DELAY * attempt + random.uniform(0, 1)
            print(
                f"Request failed for '{company_id}' ({err}). Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)
            attempt += 1

    scraper.close()
    return None, 0, False


async def scrape_all_gem_jobs(force: bool = False):
    """Scrape all companies from CSV file"""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "gem_companies.csv")

    count = 0
    successful_companies = 0
    failed_companies = 0
    skipped_companies = 0

    # Build a mapping from company_id to company name
    id_to_name = {}
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company_url = row["url"]
            company_name = row["name"]
            company_id = extract_company_id(company_url)
            id_to_name[company_id] = company_name

    companies = list(id_to_name.keys())
    print(f"Processing {len(companies)} companies...")

    for company_id in companies:
        company_name = id_to_name.get(company_id)

        print(f"\nProcessing company: {company_id}")
        data, num_jobs, was_scraped = await scrape_gem_jobs(
            company_id, force, company_name
        )

        if data is not None:
            count += num_jobs
            if was_scraped:
                successful_companies += 1
                print(f"Successfully scraped {num_jobs} jobs from {company_id}")
                await asyncio.sleep(random.uniform(MIN_SCRAPE_DELAY, MAX_SCRAPE_DELAY))
            else:
                skipped_companies += 1
        else:
            failed_companies += 1
            print(f"Failed to scrape {company_id}")

    print(
        f"\nDone! Processed {count} total jobs from {successful_companies} companies "
        f"({skipped_companies} skipped, {failed_companies} failed)"
    )
    return script_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gem job scraper")
    parser.add_argument(
        "--force", action="store_true", help="Force re-scrape all companies"
    )
    parser.add_argument(
        "company_id",
        nargs="?",
        help="Company ID to scrape (optional, scrapes all if not provided)",
    )
    args = parser.parse_args()

    start_time = time.perf_counter()
    try:
        if args.company_id:
            asyncio.run(scrape_gem_jobs(args.company_id, args.force))
        else:
            asyncio.run(scrape_all_gem_jobs(args.force))
    finally:
        elapsed = time.perf_counter() - start_time
        print(f"Total runtime: {elapsed:.2f} seconds")
