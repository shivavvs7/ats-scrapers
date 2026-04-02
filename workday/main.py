"""
Workday Job Scraper

Scrapes job postings from Workday-powered career sites using the Workday API.
Reads companies from workday_search_urls.csv and fetches all their job postings.
"""

import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from api_client import WorkdayAPIClient, JobPosting

# Configuration
CACHE_HOURS = 24
MAX_WORKERS = 10  # Parallel company scraping (increased from 5)
DELAY_BETWEEN_COMPANIES = 0.1  # Reduced delay for faster processing
SCRIPT_DIR = Path(__file__).parent
COMPANIES_DIR = SCRIPT_DIR / "companies"
SEARCH_URLS_CSV = SCRIPT_DIR / "companies.csv"
OUTPUT_JSON = SCRIPT_DIR / "workday.json"


def slugify(company_name: str, url: str) -> str:
    """Create a slug for the company from name and URL"""
    from urllib.parse import urlparse

    # Use company name as base
    slug = company_name.lower().replace(" ", "_").replace("-", "_")

    # Remove special characters
    slug = "".join(c for c in slug if c.isalnum() or c == "_")

    # Add domain part for uniqueness
    parsed = urlparse(url)
    domain_part = parsed.netloc.split(".")[0] if parsed.netloc else ""

    if domain_part and domain_part != slug:
        slug = f"{slug}_{domain_part}"

    return slug[:100]  # Limit length


def load_companies() -> List[Dict[str, str]]:
    """Load companies from workday_search_urls.csv"""
    if not SEARCH_URLS_CSV.exists():
        print(f"❌ Error: {SEARCH_URLS_CSV} not found")
        print("   Please run extract_search_urls.py first to generate company URLs")
        return []

    companies = []
    with open(SEARCH_URLS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            url = row.get("url", "").strip()

            if name and url:
                companies.append({
                    "name": name,
                    "url": url,
                    "slug": slugify(name, url)
                })

    return companies


def should_scrape_company(slug: str, force: bool) -> bool:
    """Check if company should be scraped based on cache"""
    if force:
        return True

    company_file = COMPANIES_DIR / f"{slug}.json"
    if not company_file.exists():
        return True

    try:
        with open(company_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        last_scraped_str = data.get("last_scraped")
        if not last_scraped_str:
            return True

        last_scraped = datetime.fromisoformat(last_scraped_str)
        hours_elapsed = (datetime.now() - last_scraped).total_seconds() / 3600

        return hours_elapsed >= CACHE_HOURS
    except (OSError, json.JSONDecodeError, ValueError):
        return True


def scrape_company(company: Dict[str, str], force: bool = False) -> Optional[Dict[str, Any]]:
    """
    Scrape a single company using WorkdayAPIClient

    Returns company data dict or None if failed
    """
    name = company["name"]
    url = company["url"]
    slug = company["slug"]

    # Check cache
    if not should_scrape_company(slug, force):
        company_file = COMPANIES_DIR / f"{slug}.json"
        try:
            with open(company_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            hours_ago = (datetime.now() - datetime.fromisoformat(data["last_scraped"])).total_seconds() / 3600
            print(f"  ✓ {name}: Using cached data ({hours_ago:.1f}h ago, {len(data.get('jobs', []))} jobs)")
            return data
        except (OSError, json.JSONDecodeError):
            pass

    print(f"  Scraping {name} ({url})...")

    try:
        # Create API client with faster delay (0.25s instead of default 0.5s)
        with WorkdayAPIClient(url) as client:
            # ALWAYS use unlimited method to work around 2000 result limit
            jobs_list = []
            total_reported = client.get_total_count()
            
            if total_reported > 2000:
                print(f"    Note: Company has {total_reported} jobs, will use facet subdivision to get more than 2000")
            
            for i, job in enumerate(client.get_all_jobs_unlimited(max_results=None, delay_between_requests=0.25), 1):
                jobs_list.append(job.to_dict())
                # Show progress every 500 jobs
                if i % 500 == 0:
                    progress_pct = (i / total_reported * 100) if total_reported > 0 else 0
                    print(f"    → {i} jobs fetched ({progress_pct:.1f}%)...", flush=True)
            
            # Report if we got more or less than expected
            if len(jobs_list) < total_reported:
                print(f"    ⚠ Got {len(jobs_list)} of {total_reported} jobs ({len(jobs_list)/total_reported*100:.1f}%)")

            # Create company data
            company_data = {
                "slug": slug,
                "company": name,
                "url": url,
                "job_count": len(jobs_list),
                "jobs": jobs_list,
                "last_scraped": datetime.now().isoformat(),
                "status": "success"
            }

            # Save to company file
            COMPANIES_DIR.mkdir(exist_ok=True)
            company_file = COMPANIES_DIR / f"{slug}.json"
            with open(company_file, "w", encoding="utf-8") as f:
                json.dump(company_data, f, indent=2)

            print(f"    ✓ {name}: Found {len(jobs_list)} jobs")
            return company_data

    except Exception as e:
        print(f"    ✗ {name}: Failed - {e}")

        # Save error state
        error_data = {
            "slug": slug,
            "company": name,
            "url": url,
            "job_count": 0,
            "jobs": [],
            "last_scraped": datetime.now().isoformat(),
            "status": "error",
            "error": str(e)
        }

        COMPANIES_DIR.mkdir(exist_ok=True)
        company_file = COMPANIES_DIR / f"{slug}.json"
        with open(company_file, "w", encoding="utf-8") as f:
            json.dump(error_data, f, indent=2)

        return error_data


def scrape_all_companies(force: bool = False, max_companies: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Scrape all companies from workday_search_urls.csv using parallel workers

    Returns list of company data dicts
    """
    companies = load_companies()

    if not companies:
        print("❌ No companies found in workday_search_urls.csv")
        return []

    if max_companies:
        companies = companies[:max_companies]

    print(f"\n🔍 Scraping {len(companies)} Workday companies...")
    print(f"   Using {MAX_WORKERS} parallel workers")
    print(f"   Cache: {'Disabled (force)' if force else f'{CACHE_HOURS}h'}\n")

    results = []
    completed = 0

    # Use ThreadPoolExecutor for parallel scraping
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all scraping tasks
        future_to_company = {
            executor.submit(scrape_company, company, force): company
            for company in companies
        }

        # Process completed tasks as they finish
        for future in as_completed(future_to_company):
            completed += 1
            company = future_to_company[future]

            try:
                result = future.result()
                if result:
                    results.append(result)
                print(f"[{completed}/{len(companies)}] Progress: {completed/len(companies)*100:.1f}%")
            except Exception as e:
                print(f"[{completed}/{len(companies)}] ✗ {company['name']}: Exception - {e}")

            # Small delay to avoid overwhelming the API
            if DELAY_BETWEEN_COMPANIES > 0:
                time.sleep(DELAY_BETWEEN_COMPANIES)

    return results


def create_consolidated_json(company_data_list: List[Dict[str, Any]]) -> str:
    """
    Create consolidated workday.json from all company data

    Returns path to the JSON file
    """
    # Collect all jobs
    all_jobs = []
    for company_data in company_data_list:
        for job in company_data.get("jobs", []):
            # Add company context to each job
            job_with_company = job.copy()
            job_with_company["company"] = company_data["company"]
            job_with_company["company_slug"] = company_data["slug"]
            all_jobs.append(job_with_company)

    # Create consolidated structure
    consolidated = {
        "jobs": all_jobs,
        "total_jobs": len(all_jobs),
        "total_companies": len(company_data_list),
        "successful_companies": sum(1 for c in company_data_list if c.get("status") == "success"),
        "failed_companies": sum(1 for c in company_data_list if c.get("status") == "error"),
        "last_scraped": datetime.now().isoformat()
    }

    # Save to workday.json
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(consolidated, f, indent=2)

    return str(OUTPUT_JSON)


def scrape_workday_jobs(force: bool = False, max_companies: Optional[int] = None):
    """
    Main function to scrape Workday jobs

    Args:
        force: Force re-scrape even if cached data exists
        max_companies: Limit number of companies to scrape (for testing)

    Returns:
        Tuple of (json_path, num_jobs, was_scraped)
    """
    # Check if we can use cached data
    if not force and OUTPUT_JSON.exists():
        try:
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                existing = json.load(f)

            last_scraped_str = existing.get("last_scraped")
            if last_scraped_str:
                last_scraped = datetime.fromisoformat(last_scraped_str)
                hours_elapsed = (datetime.now() - last_scraped).total_seconds() / 3600

                if hours_elapsed < CACHE_HOURS:
                    num_jobs = existing.get("total_jobs", 0)
                    print(f"✓ Using cached Workday data ({hours_elapsed:.1f}h ago, {num_jobs} jobs)")
                    return str(OUTPUT_JSON), num_jobs, False
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    # Scrape all companies
    company_data_list = scrape_all_companies(force=force, max_companies=max_companies)

    if not company_data_list:
        print("❌ No company data scraped")
        return None, 0, False

    # Create consolidated JSON
    json_path = create_consolidated_json(company_data_list)

    # Print summary
    total_jobs = sum(len(c.get("jobs", [])) for c in company_data_list)
    successful = sum(1 for c in company_data_list if c.get("status") == "success")
    failed = len(company_data_list) - successful

    print(f"\n✅ Scraping complete!")
    print(f"   Total companies: {len(company_data_list)}")
    print(f"   Successful: {successful}")
    print(f"   Failed: {failed}")
    print(f"   Total jobs: {total_jobs}")
    print(f"   Saved to: {json_path}")

    return json_path, total_jobs, True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape Workday job postings")
    parser.add_argument("--force", action="store_true", help="Force re-scrape even if cached")
    parser.add_argument("--max-companies", type=int, help="Limit number of companies (for testing)")
    args = parser.parse_args()

    scrape_workday_jobs(force=args.force, max_companies=args.max_companies)
