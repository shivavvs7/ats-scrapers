#!/usr/bin/env python3
"""
Avature Job Scraper

Scrapes job postings from Avature-powered career sites.
Works with Bloomberg, IBM, and other companies using Avature.
"""

import argparse
import csv
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

sys.path.append(str(Path(__file__).parent.parent))

from avature.api_client import AvatureCareersAPI, extract_company_name, extract_base_url

MAX_RETRIES = 3
BASE_RETRY_DELAY = 2
MIN_SCRAPE_DELAY = 1
MAX_SCRAPE_DELAY = 3


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
        should_scrape = hours_elapsed >= 12
        return should_scrape, hours_elapsed
    except (ValueError, TypeError):
        return True, None


def save_company_data(file_path: str, jobs: list, company_name: str = None) -> None:
    """Save company data with last_scraped timestamp and company name"""
    data = {
        "jobs": jobs,
        "last_scraped": datetime.now().isoformat(),
    }
    if company_name:
        data["name"] = company_name
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


def scrape_avature_jobs(
    company_url: str,
    force: bool = False,
    company_name: str = None,
):
    """
    Scrape jobs from an Avature-powered career site.
    
    Args:
        company_url: Full URL to the company's Avature site
        force: Force re-scrape even if recently scraped
        company_name: Optional company name override
        
    Returns:
        (file_path, job_count, was_scraped)
    """
    script_dir = Path(__file__).parent
    companies_dir = script_dir / "companies"
    companies_dir.mkdir(exist_ok=True)
    
    # Extract base URL and company identifier
    base_url = extract_base_url(company_url)
    
    # Create a safe filename from the URL
    safe_name = company_url.replace("https://", "").replace("http://", "")
    safe_name = safe_name.replace("/", "_").replace(".", "_")
    if len(safe_name) > 100:
        safe_name = safe_name[:100]
    
    file_path = companies_dir / f"{safe_name}.json"
    
    # Get company name
    if not company_name:
        company_name = extract_company_name(company_url)

    # Check if we should scrape
    company_data = load_company_data(file_path)
    should_scrape, hours_elapsed = should_scrape_company(company_data, force)

    if not should_scrape:
        print(f"  ✓ {company_name}: Using cached data ({hours_elapsed:.1f}h ago)")
        jobs = company_data.get("jobs", []) if company_data else []
        return str(file_path), len(jobs), False

    print(f"  Scraping {company_name} ({base_url})...")

    jobs_list = []
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with AvatureCareersAPI(base_url, rate_limit=0.5) as client:
                for i, job in enumerate(client.get_all_jobs(), 1):
                    jobs_list.append({
                        "job_id": job.job_id,
                        "title": job.title,
                        "location": job.location,
                        "department": job.department,
                        "url": job.url,
                    })
                    if i % 50 == 0:
                        print(f"    → {i} jobs fetched...", flush=True)
            
            save_company_data(file_path, jobs_list, company_name)
            print(f"  ✓ {company_name}: Found {len(jobs_list)} jobs")
            return str(file_path), len(jobs_list), True
            
        except Exception as e:
            if attempt == MAX_RETRIES:
                print(f"  ✗ {company_name}: Failed after {MAX_RETRIES} attempts: {e}")
                # Save error state
                error_data = {
                    "jobs": [],
                    "last_scraped": datetime.now().isoformat(),
                    "name": company_name,
                    "error": str(e),
                }
                with open(file_path, "w") as f:
                    json.dump(error_data, f, indent=2)
                return str(file_path), 0, False
            
            delay = BASE_RETRY_DELAY * attempt + random.uniform(0, 1)
            print(f"    Request failed ({e}). Retrying in {delay:.1f}s...")
            time.sleep(delay)

    return str(file_path), 0, False


def scrape_all_avature_jobs(force: bool = False):
    """Scrape all companies from companies.csv"""
    script_dir = Path(__file__).parent
    csv_path = script_dir / "companies.csv"

    if not csv_path.exists():
        print(f"❌ Error: {csv_path} not found")
        return

    count = 0
    successful_companies = 0
    failed_companies = 0
    skipped_companies = 0

    # Read all companies first
    companies = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("url", "").strip()
            name = row.get("name", "").strip()
            if url and "avature" in url.lower():
                companies.append((name, url))

    print(f"Processing {len(companies)} Avature companies...")

    for company_name, company_url in companies:
        print(f"\nProcessing: {company_name or 'Unknown'}")
        result, num_jobs, was_scraped = scrape_avature_jobs(
            company_url, force, company_name if company_name != "TBD" else None
        )

        if result:
            count += num_jobs
            if was_scraped:
                successful_companies += 1
                time.sleep(random.uniform(MIN_SCRAPE_DELAY, MAX_SCRAPE_DELAY))
            else:
                skipped_companies += 1
        else:
            failed_companies += 1

    print(
        f"\n✓ Done! Processed {count} total jobs from {successful_companies} companies "
        f"({skipped_companies} skipped, {failed_companies} failed)"
    )
    return str(script_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Avature job boards")
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
    parser.add_argument(
        "--name",
        help="Company name (optional)",
    )

    args = parser.parse_args()

    start_time = time.perf_counter()
    try:
        if args.company_url:
            scrape_avature_jobs(args.company_url, args.force, args.name)
        else:
            scrape_all_avature_jobs(args.force)
    finally:
        elapsed = time.perf_counter() - start_time
        print(f"Total runtime: {elapsed:.2f} seconds")
