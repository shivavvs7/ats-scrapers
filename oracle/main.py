"""
Oracle HCM Cloud (Oracle Recruiting Cloud) Job Scraper

Scrapes job listings from Oracle HCM Cloud ATS platform using the existing
OracleRecruitingClient API client.

URL Pattern: https://{subdomain}.fa.{region}.oraclecloud.com
Example: https://eeho.fa.us2.oraclecloud.com (Oracle careers)

Usage:
    python oracle/main.py [--force] [--site-number CX_45001] [url]

    # Scrape all companies from oracle_companies.csv
    python oracle/main.py

    # Force re-scrape all companies (ignore cache)
    python oracle/main.py --force

    # Scrape a single company
    python oracle/main.py https://eeho.fa.us2.oraclecloud.com

    # Scrape with custom site number
    python oracle/main.py --site-number CX_45002 https://example.fa.us2.oraclecloud.com
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

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle.scripts.oracle_ats_client.api_client import OracleRecruitingClient  # noqa: E402

# Configuration constants
MAX_RETRIES = 3
BASE_RETRY_DELAY = 2  # seconds
MIN_SCRAPE_DELAY = 1  # seconds
MAX_SCRAPE_DELAY = 3  # seconds
REQUEST_TIMEOUT = 30  # seconds
JOBS_PER_PAGE = 100  # Oracle API limit
MAX_JOBS_PER_COMPANY = 10000  # Safety limit
DEFAULT_SITE_NUMBER = "CX_45001"  # Oracle's standard site number


def parse_oracle_url(url: str) -> dict:
    """
    Parse Oracle HCM Cloud URL and extract components.

    Args:
        url: Oracle HCM Cloud URL (e.g., https://eeho.fa.us2.oraclecloud.com)

    Returns:
        Dictionary with:
            - base_url: Full base URL
            - subdomain: Subdomain (e.g., "eeho")
            - region: Region (e.g., "us2")
            - slug: Slug for file storage (e.g., "eeho-us2")
    """
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()

    # Extract subdomain and region from pattern: {subdomain}.fa.{region}.oraclecloud.com
    if ".fa." in netloc and ".oraclecloud.com" in netloc:
        parts = netloc.split(".fa.")
        subdomain = parts[0]
        region = parts[1].replace(".oraclecloud.com", "")
        base_url = f"https://{netloc}"
        slug = f"{subdomain}-{region}"

        return {
            "base_url": base_url,
            "subdomain": subdomain,
            "region": region,
            "slug": slug,
        }

    return None


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


async def scrape_oracle_jobs(
    url: str,
    force: bool = False,
    company_name: str = None,
    site_number: str = DEFAULT_SITE_NUMBER
) -> tuple[list | None, int, bool]:
    """
    Scrape jobs from a single Oracle HCM Cloud company.

    Args:
        url: Oracle HCM Cloud base URL
        force: Force re-scrape even if recently scraped
        company_name: Company name for metadata
        site_number: Oracle site number (default: CX_45001)

    Returns:
        Tuple of (jobs_list, num_jobs, was_scraped)
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    companies_dir = os.path.join(script_dir, "companies")

    if not os.path.exists(companies_dir):
        os.makedirs(companies_dir)

    # Parse URL to get slug
    url_info = parse_oracle_url(url)
    if not url_info:
        print(f"Invalid Oracle URL: {url}")
        return None, 0, False

    slug = url_info["slug"]
    base_url = url_info["base_url"]
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
        print(f"Scraped {slug} {hours_elapsed:.1f} hours ago. I will scrape again.")
    elif company_data is None:
        print(f"Company '{slug}' data file does not exist. I will scrape.")
    else:
        print(f"Company '{slug}' last_scraped field is invalid. I will scrape.")

    print(f"Fetching jobs from {base_url} (site: {site_number})...")

    # Initialize Oracle Recruiting Client
    client = OracleRecruitingClient(
        base_url=base_url,
        site_number=site_number,
        timeout=REQUEST_TIMEOUT
    )

    all_jobs = []
    attempt = 1

    while attempt <= MAX_RETRIES:
        try:
            # Pagination loop
            offset = 0
            while offset < MAX_JOBS_PER_COMPANY:
                try:
                    # Search with pagination
                    response = client.search_jobs(
                        limit=JOBS_PER_PAGE,
                        offset=offset,
                        sort_by="POSTING_DATES_DESC"
                    )

                    # Extract jobs from response
                    jobs = client.extract_jobs_from_response(response)

                    if not jobs:
                        # No more jobs
                        break

                    all_jobs.extend(jobs)
                    print(f"  Fetched {len(jobs)} jobs (offset: {offset}, total: {len(all_jobs)})")

                    # Check if we've reached the end
                    if len(jobs) < JOBS_PER_PAGE:
                        # Last page
                        break

                    offset += JOBS_PER_PAGE

                    # Small delay between pagination requests
                    await asyncio.sleep(0.5)

                except Exception as e:
                    print(f"  Error fetching jobs at offset {offset}: {e}")
                    # Continue to next page if we have some data
                    if all_jobs:
                        break
                    raise

            # Success - save and return
            config = {
                "subdomain": url_info["subdomain"],
                "region": url_info["region"],
                "site_number": site_number,
            }
            save_company_data(file_path, all_jobs, company_name, config)
            return all_jobs, len(all_jobs), True

        except Exception as err:
            if attempt == MAX_RETRIES:
                print(f"Exceeded retries for '{slug}' due to error: {err}")
                return None, 0, False

            delay = BASE_RETRY_DELAY * attempt + random.uniform(0, 1)
            print(f"Request failed for '{slug}' ({err}). Retrying in {delay:.1f}s...")
            await asyncio.sleep(delay)
            attempt += 1

    return None, 0, False


async def scrape_all_oracle_jobs(force: bool = False, site_number: str = DEFAULT_SITE_NUMBER):
    """Scrape all Oracle HCM Cloud companies from oracle_companies.csv"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "oracle_companies.csv")

    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        print("Please run discovery first:")
        print("  python searxng_discovery.py --platform oracle")
        return

    count = 0
    successful_companies = 0
    failed_companies = 0
    skipped_companies = 0

    # Build mapping from URL to company name
    url_to_name = {}
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company_url = row["url"]
            company_name = row["name"]
            url_to_name[company_url.lower().strip().rstrip("/")] = company_name

    companies = list(url_to_name.keys())
    print(f"Processing {len(companies)} companies...")

    for company_url in companies:
        company_name = url_to_name.get(company_url)

        # Parse URL to get slug
        url_info = parse_oracle_url(company_url)
        if not url_info:
            print(f"\nSkipping invalid URL: {company_url}")
            failed_companies += 1
            continue

        slug = url_info["slug"]

        print(f"\nProcessing company: {slug} ({company_name})")
        data, num_jobs, was_scraped = await scrape_oracle_jobs(
            company_url, force, company_name, site_number
        )

        if data is not None:
            count += num_jobs
            if was_scraped:
                successful_companies += 1
                print(f"Successfully scraped {num_jobs} jobs from {slug}")
                await asyncio.sleep(random.uniform(MIN_SCRAPE_DELAY, MAX_SCRAPE_DELAY))
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Oracle HCM Cloud job scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape all companies
  python oracle/main.py

  # Force re-scrape all companies
  python oracle/main.py --force

  # Scrape single company
  python oracle/main.py https://eeho.fa.us2.oraclecloud.com

  # Scrape with custom site number
  python oracle/main.py --site-number CX_45002 https://example.fa.us2.oraclecloud.com
        """
    )
    parser.add_argument(
        "--force", action="store_true", help="Force re-scrape all companies"
    )
    parser.add_argument(
        "--site-number",
        type=str,
        default=DEFAULT_SITE_NUMBER,
        help=f"Oracle site number (default: {DEFAULT_SITE_NUMBER})"
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="Oracle HCM Cloud URL to scrape (optional, scrapes all if not provided)",
    )
    args = parser.parse_args()

    start_time = time.perf_counter()
    try:
        if args.url:
            asyncio.run(
                scrape_oracle_jobs(args.url, args.force, site_number=args.site_number)
            )
        else:
            asyncio.run(scrape_all_oracle_jobs(args.force, args.site_number))
    finally:
        elapsed = time.perf_counter() - start_time
        print(f"Total runtime: {elapsed:.2f} seconds")
