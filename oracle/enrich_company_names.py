"""
Enrich Oracle company names by scraping the actual company names from their careers pages.

This script reads oracle_companies.csv, fetches the real company name from each Oracle
HCM Cloud careers page, and updates the CSV with the actual company names.
"""

import csv
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle.scripts.oracle_ats_client.api_client import OracleRecruitingClient  # noqa: E402


def extract_company_name_from_html(url: str, site_number: str = "CX_45001") -> str | None:
    """
    Extract company name from Oracle careers page HTML.

    Tries multiple strategies:
    1. Look for site title/header
    2. Look for og:site_name meta tag
    3. Look for company name in page title
    """
    try:
        # Construct the proper careers page URL
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        careers_url = f"{base_url}/hcmUI/CandidateExperience/en/sites/{site_number}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(careers_url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Strategy 1: og:site_name meta tag
        og_site = soup.find('meta', property='og:site_name')
        if og_site and og_site.get('content'):
            name = og_site.get('content').strip()
            # Filter out generic/default names
            if name and name.lower() not in ['careers', 'jobs', 'oracle', 'candidate experience site']:
                return name

        # Strategy 2: Look for site title in header
        site_title = soup.find('h1', class_='site-title')
        if site_title:
            name = site_title.get_text(strip=True)
            if name and name.lower() not in ['careers', 'jobs', 'oracle']:
                return name

        # Strategy 3: Page title - extract before "Careers" or "Jobs"
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Try to extract company name from patterns like "Company Name Careers" or "Company - Careers"
            for separator in [' - Careers', ' Careers', '| Careers', ' - Jobs', ' Jobs', '| Jobs']:
                if separator in title:
                    name = title.split(separator)[0].strip()
                    if name and name.lower() != 'oracle':
                        return name

        # Strategy 4: Look for company branding in header/nav
        for selector in ['[class*="company-name"]', '[class*="brand"]', 'header h1', 'nav h1']:
            elem = soup.select_one(selector)
            if elem:
                name = elem.get_text(strip=True)
                if name and len(name) > 2 and name.lower() not in ['careers', 'jobs', 'oracle', 'home']:
                    return name

        return None

    except Exception as e:
        print(f"  ⚠️  Error fetching HTML: {e}")
        return None


def extract_company_name_from_api(base_url: str, site_number: str = "CX_45001") -> str | None:
    """
    Try to extract company name by fetching a sample job and looking at job metadata.
    """
    try:
        client = OracleRecruitingClient(base_url, site_number, timeout=10)
        response = client.search_jobs(limit=1)
        jobs = client.extract_jobs_from_response(response)

        if jobs and len(jobs) > 0:
            job = jobs[0]

            # Try OrganizationName field
            if job.get('OrganizationName'):
                return job['OrganizationName']

            # Try to extract from job title patterns
            # Some companies put their name in titles like "Software Engineer - CompanyName"

        return None

    except Exception as e:
        print(f"  ⚠️  Error fetching from API: {e}")
        return None


def parse_oracle_url(url: str) -> dict:
    """Parse Oracle HCM Cloud URL and extract components."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()

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


def enrich_company_names(csv_path: str, delay: float = 2.0):
    """
    Enrich company names in oracle_companies.csv by scraping actual names.

    Args:
        csv_path: Path to oracle_companies.csv
        delay: Delay between requests in seconds
    """
    if not Path(csv_path).exists():
        print(f"❌ CSV file not found: {csv_path}")
        return

    # Read existing CSV
    companies = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            companies.append(row)

    print(f"📊 Enriching {len(companies)} companies...")
    print(f"⏱️  Delay between requests: {delay}s\n")

    enriched_count = 0
    failed_count = 0

    for i, company in enumerate(companies, 1):
        url = company['url']
        current_name = company['name']

        # Parse URL
        url_info = parse_oracle_url(url)
        if not url_info:
            print(f"[{i}/{len(companies)}] ⚠️  Invalid URL: {url}")
            failed_count += 1
            continue

        slug = url_info['slug']
        subdomain = url_info['subdomain']

        # Skip if name doesn't look like a subdomain ID
        # (already has a good name)
        if len(current_name) > 10 or ' ' in current_name or current_name.lower() not in subdomain.lower():
            print(f"[{i}/{len(companies)}] ✓ {current_name} (already enriched)")
            continue

        print(f"[{i}/{len(companies)}] 🔍 Enriching: {slug} ({url})")

        # Determine site number (default to CX_45001)
        site_number = "CX_45001"  # Could be enhanced to read from config if available

        # Try HTML scraping first
        new_name = extract_company_name_from_html(url, site_number)

        # Fallback to API if HTML didn't work
        if not new_name:
            print(f"  💡 Trying API fallback...")
            new_name = extract_company_name_from_api(url_info['base_url'])

        if new_name and new_name.lower() != 'candidate experience site':
            print(f"  ✨ Found name: {new_name}")
            company['name'] = new_name
            enriched_count += 1
        else:
            if new_name and new_name.lower() == 'candidate experience site':
                print(f"  ⚠️  Generic name found, keeping: {current_name}")
            else:
                print(f"  ⚠️  Could not find company name, keeping: {current_name}")
            failed_count += 1

        # Delay between requests to be polite
        if i < len(companies):
            time.sleep(delay)

    # Write back to CSV
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'url'])
        writer.writeheader()
        writer.writerows(companies)

    print(f"\n📊 Summary:")
    print(f"  ✅ Enriched: {enriched_count}")
    print(f"  ⚠️  Failed: {failed_count}")
    print(f"  📁 Saved to: {csv_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Enrich Oracle company names by scraping actual names from careers pages"
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="oracle/oracle_companies.csv",
        help="Path to oracle_companies.csv (default: oracle/oracle_companies.csv)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between requests in seconds (default: 2.0)"
    )

    args = parser.parse_args()

    enrich_company_names(args.csv, args.delay)
