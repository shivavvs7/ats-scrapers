#!/usr/bin/env python3
"""
Personio Jobs Scraper

Scrapes job postings from Personio job boards and saves them to JSON files.
Follows the same pattern as other scrapers (ashby, greenhouse, etc.) for easy integration.
"""

import asyncio
import argparse
import csv
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Tuple

sys.path.append(str(Path(__file__).parent.parent))

from personio.api_client import PersonioAPI, PersonioAPIError, PersonioParseError

MAX_RETRIES = 3
BASE_RETRY_DELAY = 2  # seconds
MIN_SCRAPE_DELAY = 1  # seconds
MAX_SCRAPE_DELAY = 3  # seconds

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def extract_company_slug(url: str) -> str:
    """Extract company slug from Personio job board URL."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # Handle company subdomains: company.jobs.personio.com -> company
    if ".jobs.personio." in hostname:
        subdomain = hostname.split(".")[0]
        return subdomain

    # Handle main site: www.personio.com -> personio-main
    if "www.personio.com" in hostname or "personio.com" == hostname:
        return "personio-main"

    # Fallback: use hostname as slug
    return hostname.replace(".", "-") if hostname else "unknown"


def load_company_data(file_path: str) -> dict | None:
    """Load company data from JSON file."""
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


def save_company_data(
    file_path: str, jobs_data: list, company_name: str = None
) -> None:
    """Save company data with last_scraped timestamp and company name."""
    data = {
        "jobs": [job.model_dump(exclude_none=True) for job in jobs_data],
        "last_scraped": datetime.now().isoformat(),
    }
    if company_name:
        data["name"] = company_name
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


async def scrape_personio_jobs(
    company_url: str, force: bool = False, company_name: str = None
) -> Tuple[Optional[str], int, bool]:
    """
    Scrape Personio jobs for a company.

    Args:
        company_url: URL to the Personio job board
        force: If True, force re-scrape even if recently scraped
        company_name: Optional company name for saving

    Returns:
        Tuple of (file_path, num_jobs, was_scraped)
        - file_path: Path to saved JSON file, or None if failed
        - num_jobs: Number of jobs found
        - was_scraped: True if actually scraped, False if skipped due to caching
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    companies_dir = os.path.join(script_dir, "companies")

    if not os.path.exists(companies_dir):
        os.makedirs(companies_dir)

    company_slug = extract_company_slug(company_url)
    file_path = os.path.join(companies_dir, f"{company_slug}.json")

    # Check if we should scrape this company
    company_data = load_company_data(file_path)
    should_scrape, hours_elapsed = should_scrape_company(company_data, force)

    if not should_scrape:
        print(
            f"Scraped {company_slug} {hours_elapsed:.1f} hours ago. I will not scrape again."
        )
        # Return existing data info with skipped flag
        num_jobs = len(company_data.get("jobs", [])) if company_data else 0
        return file_path, num_jobs, False  # False = not scraped (skipped)

    # Log decision to scrape
    if force:
        print(f"Forcing scrape for '{company_slug}' (force=True).")
    elif hours_elapsed is not None:
        print(
            f"Scraped {company_slug} {hours_elapsed:.1f} hours ago. I will scrape again."
        )
    elif company_data is None:
        print(f"Company '{company_slug}' data file does not exist. I will scrape.")
    elif not company_data.get("last_scraped"):
        print(f"Company '{company_slug}' has no last_scraped field. I will scrape.")
    else:
        print(f"Company '{company_slug}' last_scraped field is invalid. I will scrape.")

    print(f"Fetching fresh data from {company_url}...")

    attempt = 1
    while attempt <= MAX_RETRIES:
        try:
            # Use synchronous PersonioAPI in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            client = PersonioAPI(base_url=company_url, timeout=30)
            jobs = await loop.run_in_executor(None, client.get_all_jobs)
            client.close()

            # Save with last_scraped timestamp and company name, even if empty
            # This marks that we successfully checked (even if no jobs found)
            save_company_data(file_path, jobs, company_name)

            if len(jobs) == 0:
                print(
                    f"No jobs found for '{company_slug}' (this is normal if company has no open positions)"
                )

            return file_path, len(jobs), True  # True = scraped
        except PersonioAPIError as err:
            if attempt == MAX_RETRIES:
                print(f"Exceeded retries for '{company_slug}' due to API error: {err}")
                return None, 0, False
            delay = BASE_RETRY_DELAY * attempt + random.uniform(0, 1)
            print(
                f"Request failed for '{company_slug}' ({err}). Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)
            attempt += 1
        except PersonioParseError as err:
            # Don't retry on parse errors - they're usually permanent (wrong format, etc.)
            print(f"Parse error for '{company_slug}': {err}")
            return None, 0, False
        except Exception as err:
            if attempt == MAX_RETRIES:
                print(f"Exceeded retries for '{company_slug}' due to error: {err}")
                return None, 0, False
            delay = BASE_RETRY_DELAY * attempt + random.uniform(0, 1)
            print(
                f"Request failed for '{company_slug}' ({err}). Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)
            attempt += 1

    return None, 0, False


async def scrape_all_personio_jobs(force: bool = False):
    """Scrape all Personio companies from personio_companies.csv."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "personio_companies.csv")

    if not os.path.exists(csv_path):
        print(f"Companies CSV not found at {csv_path}")
        return script_dir

    count = 0
    successful_companies = 0
    failed_companies = 0
    skipped_companies = 0

    # Build a mapping from URL to company name
    url_to_name = {}
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company_url = row["url"]
            company_name = row["name"]
            url_to_name[company_url] = company_name

    companies = list(url_to_name.keys())
    print(f"Processing {len(companies)} companies...")

    for company_url in companies:
        company_name = url_to_name.get(company_url)

        print(f"\nProcessing company: {company_url}")
        result, num_jobs, was_scraped = await scrape_personio_jobs(
            company_url, force, company_name
        )

        if result is not None:
            count += num_jobs
            if was_scraped:
                successful_companies += 1
                print(
                    f"{GREEN}Successfully scraped {num_jobs} jobs from {company_url}{RESET}"
                )
                # Delay only if we scraped successfully
                await asyncio.sleep(random.uniform(MIN_SCRAPE_DELAY, MAX_SCRAPE_DELAY))
            else:
                skipped_companies += 1
        else:
            failed_companies += 1
            print(f"{RED}Failed to scrape {company_url}{RESET}")

    print(
        f"\nDone! Processed {count} total jobs from {successful_companies} companies "
        f"({skipped_companies} skipped, {failed_companies} failed)"
    )
    return script_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape Personio job boards and optionally process to database"
    )
    parser.add_argument(
        "company_url",
        nargs="?",
        help="Company URL to scrape (optional, scrapes all if not provided)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-scrape all companies",
    )

    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    start_time = time.perf_counter()
    try:
        if args.company_url:
            asyncio.run(scrape_personio_jobs(args.company_url, args.force))
        else:
            script_dir = asyncio.run(scrape_all_personio_jobs(args.force))
    finally:
        elapsed = time.perf_counter() - start_time
        print(f"Total runtime: {elapsed:.2f} seconds")
