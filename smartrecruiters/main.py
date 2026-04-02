import asyncio
import argparse
import csv
import json
import os
import random
import time
from datetime import datetime
from urllib.parse import urlparse

import aiohttp

MAX_RETRIES = 3
BASE_RETRY_DELAY = 2  # seconds
MIN_SCRAPE_DELAY = 1  # seconds
MAX_SCRAPE_DELAY = 3  # seconds


def extract_company_slug(url: str) -> str:
    """Extract company slug from SmartRecruiters job board URL"""
    parsed = urlparse(url)
    # Extract the path and remove leading slash
    path = parsed.path.lstrip("/")
    # Remove trailing slash if present
    path = path.rstrip("/")
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


def save_company_data(file_path: str, api_data: dict, company_name: str = None) -> None:
    """Save company data with last_scraped timestamp and company name"""
    api_data["last_scraped"] = datetime.now().isoformat()
    if company_name:
        api_data["name"] = company_name
    with open(file_path, "w") as f:
        json.dump(api_data, f, indent=2)


async def scrape_company_jobs(
    company_slug: str, force: bool = False, company_name: str = None
):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    companies_dir = os.path.join(script_dir, "companies")

    if not os.path.exists(companies_dir):
        os.makedirs(companies_dir)

    file_path = os.path.join(companies_dir, f"{company_slug}.json")

    # Check if we should scrape this company
    company_data = load_company_data(file_path)
    should_scrape, hours_elapsed = should_scrape_company(company_data, force)

    if not should_scrape:
        print(
            f"Scraped {company_slug} {hours_elapsed:.1f} hours ago. I will not scrape again."
        )
        # Return existing data info with skipped flag
        num_jobs = len(company_data.get("content", []))
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

    base_url = f"https://api.smartrecruiters.com/v1/companies/{company_slug}/postings"
    limit = 100  # Maximum limit per request
    offset = 0
    all_content = []
    total_found = None

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        while True:
            url = f"{base_url}?limit={limit}&offset={offset}"
            if offset == 0:
                print(f"Fetching fresh data from {base_url}...")
            else:
                print(f"Fetching page {offset // limit + 1} (offset={offset})...")

            attempt = 1
            page_fetched = False
            done_paginating = False
            
            while attempt <= MAX_RETRIES:
                try:
                    async with session.get(url) as response:
                        if response.status == 404:
                            if offset == 0:
                                print(f"Company '{company_slug}' not found (404)")
                                return None, 0, False
                            else:
                                # If 404 on later pages, we've reached the end
                                done_paginating = True
                                break

                        if response.status != 200:
                            if offset == 0:
                                print(f"Error {response.status} for company '{company_slug}'")
                                return None, 0, False
                            else:
                                # If error on later pages, stop pagination
                                print(f"Error {response.status} on page {offset // limit + 1}, stopping pagination")
                                done_paginating = True
                                break

                        try:
                            data = await response.json()
                        except aiohttp.client_exceptions.ContentTypeError as e:
                            if offset == 0:
                                print(f"Failed to parse JSON for company '{company_slug}': {e}")
                                return None, 0, False
                            else:
                                print(f"Failed to parse JSON on page {offset // limit + 1}: {e}")
                                done_paginating = True
                                break

                        # Extract content and metadata
                        page_content = data.get("content", [])
                        all_content.extend(page_content)

                        # Get total found on first page
                        if total_found is None:
                            total_found = data.get("totalFound", len(page_content))
                            print(f"Total jobs found: {total_found}")

                        page_fetched = True
                        
                        # Check if we've fetched all pages
                        if len(page_content) == 0 or offset + limit >= total_found:
                            # No more pages to fetch
                            done_paginating = True
                            break
                        
                        # Move to next page
                        offset += limit
                        break

                except (
                    aiohttp.client_exceptions.ClientPayloadError,
                    aiohttp.ClientError,
                    aiohttp.http_exceptions.HttpProcessingError,
                ) as err:
                    if attempt == MAX_RETRIES:
                        print(
                            f"Exceeded retries for '{company_slug}' page {offset // limit + 1} due to network error: {err}"
                        )
                        # If first page fails completely, return error
                        if offset == 0:
                            return None, 0, False
                        # Otherwise, stop pagination and return what we have
                        done_paginating = True
                        break
                    delay = BASE_RETRY_DELAY * attempt + random.uniform(0, 1)
                    print(
                        f"Request failed for '{company_slug}' page {offset // limit + 1} ({err}). Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                    attempt += 1

            if not page_fetched or done_paginating:
                # Failed to fetch page after retries, or we're done paginating
                break

            # Small delay between pages to be respectful
            await asyncio.sleep(random.uniform(0.5, 1.5))

        # Combine all pages into a single response structure
        combined_data = {
            "content": all_content,
            "totalFound": total_found or len(all_content),
            "limit": limit,
            "offset": 0,
        }

        # Save with last_scraped timestamp and company name
        save_company_data(file_path, combined_data, company_name)

        num_jobs = len(all_content)
        print(f"Successfully fetched {num_jobs} jobs from {company_slug}")
        return file_path, num_jobs, True  # True = scraped


async def scrape_all_smartrecruiters_jobs(force: bool = False):
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "smartrecruiters_companies.csv")

    count = 0
    successful_companies = 0
    failed_companies = 0
    skipped_companies = 0

    # Build a mapping from slug to company name
    slug_to_name = {}
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company_url = row["url"]
            company_name = row["name"]
            company_slug = extract_company_slug(company_url)
            slug_to_name[company_slug] = company_name

    companies = list(slug_to_name.keys())
    print(f"Processing {len(companies)} companies...")

    for company_slug in companies:
        company_name = slug_to_name.get(company_slug)

        print(f"\nProcessing company: {company_slug}")
        result, num_jobs, was_scraped = await scrape_company_jobs(
            company_slug, force, company_name
        )

        if result is not None:
            count += num_jobs
            if was_scraped:
                successful_companies += 1
                print(f"Successfully scraped {num_jobs} jobs from {company_slug}")
                # Delay only if we scraped successfully
                await asyncio.sleep(random.uniform(MIN_SCRAPE_DELAY, MAX_SCRAPE_DELAY))
            else:
                skipped_companies += 1
        else:
            failed_companies += 1
            print(f"Failed to scrape {company_slug}")

    print(
        f"\nDone! Processed {count} total jobs from {successful_companies} companies "
        f"({skipped_companies} skipped, {failed_companies} failed)"
    )
    return script_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SmartRecruiters job scraper")
    parser.add_argument(
        "--force", action="store_true", help="Force re-scrape all companies"
    )
    parser.add_argument(
        "company_slug",
        nargs="?",
        help="Company slug to scrape (optional, scrapes all if not provided)",
    )
    args = parser.parse_args()

    start_time = time.perf_counter()
    try:
        if args.company_slug:
            asyncio.run(scrape_company_jobs(args.company_slug, args.force))
        else:
            asyncio.run(scrape_all_smartrecruiters_jobs(args.force))
    finally:
        elapsed = time.perf_counter() - start_time
        print(f"Total runtime: {elapsed:.2f} seconds")
