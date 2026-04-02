#!/usr/bin/env python3
"""
Mercor Jobs Scraper

Scrapes job postings from Mercor's work platform and saves them to mercor.json.
Follows the same pattern as other scrapers (google, apple, cursor, etc.) for easy integration.

Mercor is a talent marketplace where companies post contract/job opportunities.
"""

import json
import os
import re
import sys
import importlib.util
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Import api_client from the mercor directory using importlib to avoid conflicts
script_dir = Path(__file__).resolve().parent
api_client_path = script_dir / "api_client.py"
spec = importlib.util.spec_from_file_location("mercor_api_client", api_client_path)
mercor_api_client = importlib.util.module_from_spec(spec)
sys.modules["mercor_api_client"] = mercor_api_client
spec.loader.exec_module(mercor_api_client)
MercorClient = mercor_api_client.MercorClient
MercorAPIError = mercor_api_client.MercorAPIError

BASE_URL = "https://work.mercor.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; StapplyMap/1.0)"}

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = SCRIPT_DIR / "mercor.json"


def slugify(text: str) -> str:
    """Convert title to URL-friendly slug."""
    # Remove special characters and convert to lowercase
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    # Replace spaces with hyphens
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')
    return slug


def construct_job_url(listing_id: str, title: str) -> str:
    """Construct the job detail URL from listing ID and title."""
    slug = slugify(title)
    return f"{BASE_URL}/jobs/{listing_id}/{slug}"


def fetch_job_description(job_url: str) -> Optional[str]:
    """
    Fetch the job description from the job detail page.
    
    The description is available in:
    1. The __NEXT_DATA__ script tag (JSON with full job data)
    2. The JSON-LD structured data
    
    Returns the description as markdown-ish text, or None if not found.
    """
    try:
        response = requests.get(job_url, headers=HEADERS, timeout=15, allow_redirects=True)
        response.raise_for_status()
        html = response.text
        
        # Parse the __NEXT_DATA__ JSON which contains all job details
        soup = BeautifulSoup(html, "html.parser")
        next_data_script = soup.find("script", {"id": "__NEXT_DATA__"})
        
        if next_data_script:
            try:
                data = json.loads(next_data_script.string)
                # Navigate to the job description in the Next.js data structure
                page_props = data.get("props", {}).get("pageProps", {})
                role = page_props.get("role", {})
                description = role.get("description")
                if description:
                    return description
            except (json.JSONDecodeError, KeyError, AttributeError):
                pass
        
        # Fallback: Try to get from JSON-LD structured data
        json_ld_script = soup.find("script", {"type": "application/ld+json"})
        if json_ld_script:
            try:
                data = json.loads(json_ld_script.string)
                if data.get("@type") == "JobPosting":
                    return data.get("description")
            except (json.JSONDecodeError, AttributeError):
                pass
        
        return None
        
    except requests.RequestException:
        return None


def format_job_data(listing: Dict[str, Any]) -> Dict[str, Any]:
    """Format a Mercor listing into the standard job format."""
    listing_id = listing.get("listingId", "")
    title = listing.get("title", "")
    company = listing.get("companyName", "Mercor")
    location = listing.get("location", "")
    
    # Construct the job URL
    job_url = construct_job_url(listing_id, title)
    
    # Format rate information if available
    rate_min = listing.get("rateMin")
    rate_max = listing.get("rateMax")
    pay_rate_frequency = listing.get("payRateFrequency", "hourly")
    
    job_data = {
        "url": job_url,
        "title": title,
        "location": location,
        "company": company,
        "listingId": listing_id,
        "rateMin": rate_min,
        "rateMax": rate_max,
        "payRateFrequency": pay_rate_frequency,
        "postedAt": listing.get("postedAt"),
        "listingDomain": listing.get("listingDomain"),
        "commitment": listing.get("commitment"),
    }
    
    return job_data


def scrape_mercor_jobs(force: bool = False, sleep_s: float = 0.5) -> tuple[str, int, bool]:
    """
    Scrape Mercor jobs and store them in mercor/mercor.json.
    Returns (json_path, num_jobs, was_scraped).
    
    Args:
        force: If True, force scraping even if data was recently scraped
        sleep_s: Sleep time between requests (not used for API calls but kept for interface consistency)
        
    Returns:
        Tuple of (json_path_str, num_jobs, was_scraped)
    """
    # Check if file exists and is fresh (unless force=True)
    # Default freshness: 12 hours (similar to Cursor)
    max_age_hours = 12.0
    if not force and OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)

            if isinstance(existing, dict):
                last_scraped_str = existing.get("last_scraped")
                jobs = existing.get("jobs", [])
            else:
                last_scraped_str = None
                jobs = existing

            if last_scraped_str:
                try:
                    last_scraped = datetime.fromisoformat(last_scraped_str)
                    hours_elapsed = (
                        datetime.now() - last_scraped
                    ).total_seconds() / 3600
                    if hours_elapsed < max_age_hours:
                        print(
                            f"Existing Mercor data scraped {hours_elapsed:.1f} hours ago. Reusing."
                        )
                        return str(OUTPUT_FILE), len(jobs), False
                    else:
                        print(
                            f"Existing Mercor data is stale ({hours_elapsed:.1f} hours old). Rescraping..."
                        )
                except Exception:
                    pass
        except Exception:
            pass

    print("[*] Fetching Mercor job listings from API")
    
    # Initialize the API client
    client = MercorClient()
    
    try:
        listings = client.get_job_listings()
    except MercorAPIError as e:
        print(f"[✗] Failed to fetch Mercor jobs: {e}")
        return str(OUTPUT_FILE), 0, True
    
    print(f"[*] Found {len(listings)} Mercor listings")
    
    if not listings:
        print("[*] No jobs found")
        return str(OUTPUT_FILE), 0, True
    
    # Process each job - fetch descriptions
    jobs = []
    for i, listing in enumerate(listings, 1):
        job_data = format_job_data(listing)
        print(f"    [{i}/{len(listings)}] {job_data['title']} @ {job_data['company']}")
        
        # Fetch the full description from the job page
        description = fetch_job_description(job_data["url"])
        job_data["description"] = description
        
        jobs.append(job_data)
    
    # Wrap the output with metadata
    wrapped = {
        "last_scraped": datetime.now().isoformat(),
        "name": "Mercor",
        "jobs": jobs,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(wrapped, f, indent=2, ensure_ascii=False)

    print(f"[✓] Saved {len(jobs)} Mercor jobs to {OUTPUT_FILE}")
    return str(OUTPUT_FILE), len(jobs), True


if __name__ == "__main__":
    scrape_mercor_jobs(force=True)
