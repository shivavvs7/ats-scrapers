"""
Extract Workday Search URLs

This script processes workday_companies.csv to extract unique company domains,
searches for job listings using SearXNG, and extracts the base search page URL
from the search results.
"""

import pandas as pd
import os
import re
import time
from urllib.parse import urlparse, urlunparse
from typing import Optional, Tuple, List, Dict
from dotenv import load_dotenv

# Import SearXNG search function
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from searxng_discovery import search_searxng, PRIMARY_ENGINE

load_dotenv()

# Default delay between requests
DEFAULT_DELAY = float(os.getenv("SEARXNG_REQUEST_DELAY", "1.0"))


def extract_domain_from_url(url: str) -> Optional[str]:
    """Extract domain from Workday URL."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        
        # Check if it's a Workday domain
        if ".myworkdayjobs.com" in netloc:
            return netloc
        return None
    except Exception:
        return None


def extract_unique_companies_and_domains(csv_path: str) -> Dict[str, str]:
    """
    Extract unique companies and their domains from CSV.
    
    Returns:
        Dictionary mapping company name to domain
    """
    df = pd.read_csv(csv_path)
    
    # Group by company name and get first unique domain
    companies = {}
    
    for _, row in df.iterrows():
        company_name = row['name']
        url = row['url']
        
        domain = extract_domain_from_url(url)
        if domain and company_name not in companies:
            companies[company_name] = domain
    
    return companies


def normalize_search_url(url: str) -> Optional[str]:
    """
    Normalize a Workday URL to extract the base search page URL.

    Examples:
        https://3m.wd1.myworkdayjobs.com/en-US/Search/details/...
        -> https://3m.wd1.myworkdayjobs.com/Search

        https://akumincorp.wd5.myworkdayjobs.com/en-US/akumincareers/job/...
        -> https://akumincorp.wd5.myworkdayjobs.com/akumincareers

        https://3m.wd1.myworkdayjobs.com/Search
        -> https://3m.wd1.myworkdayjobs.com/Search
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path

        # Check if it's a Workday domain
        if ".myworkdayjobs.com" not in domain:
            return None

        # Remove language codes (e.g., /en-US/, /en-us/, /ja-jp/)
        # Pattern: /{lang-code}/ where lang-code is 2-5 chars with optional hyphen
        path = re.sub(r'^/[a-z]{2}(?:-[a-z]{2})?/', '/', path, flags=re.IGNORECASE)

        # Remove trailing slash
        path = path.rstrip('/')

        # Split path into segments
        path_segments = [p for p in path.split('/') if p]

        if not path_segments:
            return None

        # Extract the career site name (first path segment)
        # This could be "Search", "akumincareers", "adgcareers", etc.
        career_site_name = path_segments[0]

        # Skip if it's a job-specific path
        if career_site_name.lower() in ['job', 'details', 'apply']:
            return None

        # Construct normalized URL with just the career site name
        path = f'/{career_site_name}'

        normalized = urlunparse((
            'https',
            domain,
            path,
            '',  # params
            '',  # query
            ''   # fragment
        ))

        return normalized

    except Exception as e:
        print(f"    ⚠️  Error normalizing URL {url}: {e}")
        return None


def is_job_board_url(url: str) -> bool:
    """Check if URL is a job board/search page (not a job listing)."""
    path = urlparse(url).path.lower()
    # Check if it's NOT a job listing (doesn't contain /job/, /details/, /apply/)
    return '/job/' not in path and '/details/' not in path and '/apply/' not in path


def is_job_listing_url(url: str) -> bool:
    """Check if URL is a job listing."""
    path = urlparse(url).path.lower()
    return '/job/' in path or '/details/' in path or '/apply/' in path


def find_search_url_from_results(results: List[dict], domain: str) -> Optional[Tuple[str, str]]:
    """
    Find search URL from SearXNG results.
    
    Returns:
        Tuple of (search_url, result_type) or None if not found
        result_type is either "job_board" or "job_listing"
    """
    if not results:
        return None
    
    # First, look for job board URLs (preferred)
    for result in results:
        url = result.get('url', '')
        if not url or domain not in url.lower():
            continue
        
        if is_job_board_url(url):
            normalized = normalize_search_url(url)
            if normalized:
                return (normalized, "job_board")
    
    # Then look for job listing URLs
    for result in results:
        url = result.get('url', '')
        if not url or domain not in url.lower():
            continue
        
        if is_job_listing_url(url):
            normalized = normalize_search_url(url)
            if normalized:
                return (normalized, "job_listing")
    
    return None


def main():
    """Main function to extract search URLs."""
    # Get paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, 'workday_companies.csv')
    output_path = os.path.join(script_dir, 'workday_search_urls.csv')
    
    # Check if input CSV exists
    if not os.path.exists(csv_path):
        print(f"❌ Error: {csv_path} not found")
        return
    
    # Check for SearXNG URL
    searxng_url = os.getenv("SEARXNG_URL")
    if not searxng_url:
        print("❌ Error: SEARXNG_URL environment variable not set")
        print("   Please set SEARXNG_URL in your .env file")
        return
    
    print(f"🔍 Extracting unique companies from {csv_path}...")
    companies = extract_unique_companies_and_domains(csv_path)
    print(f"   Found {len(companies)} unique companies")

    # Load existing results if CSV exists
    existing_domains = set()
    results = []
    if os.path.exists(output_path):
        print(f"\n📂 Loading existing results from {output_path}...")
        df_existing = pd.read_csv(output_path)
        # Convert to internal format with domain extracted from URL
        for _, row in df_existing.iterrows():
            url = row.get('url')
            if pd.notna(url) and '.myworkdayjobs.com' in str(url):
                domain = extract_domain_from_url(url)
                if domain:
                    existing_domains.add(domain)
                    results.append({
                        'company_name': row['name'],
                        'search_url': url
                    })
        print(f"   Found {len(results)} existing results")
        print(f"   Skipping {len(existing_domains)} already processed companies")

    # Filter out companies we already have
    companies_to_process = {name: domain for name, domain in companies.items()
                           if domain not in existing_domains}

    print(f"\n🔍 Searching for job URLs using SearXNG ({searxng_url})...")
    print(f"   Using engines: {PRIMARY_ENGINE}")
    print(f"   Delay between requests: {DEFAULT_DELAY}s")
    print(f"   Companies to process: {len(companies_to_process)}/{len(companies)}\n")

    total = len(companies)
    processed_count = len(existing_domains)

    for idx, (company_name, domain) in enumerate(companies.items(), 1):
        # Skip if already processed
        if domain in existing_domains:
            continue

        print(f"[{idx}/{total}] {company_name} ({domain})")

        # Search for jobs
        query = f"site:{domain} job"
        search_results = search_searxng(
            searxng_url=searxng_url,
            query=query,
            page=1,
            engines=PRIMARY_ENGINE,
            max_retries=3
        )
        
        if not search_results:
            print(f"    ⚠️  No search results found")
            results.append({
                'company_name': company_name,
                'search_url': None
            })
        else:
            # Find search URL from results
            found = find_search_url_from_results(search_results, domain)

            if found:
                search_url, result_type = found
                print(f"    ✓ Found {result_type}: {search_url}")
                results.append({
                    'company_name': company_name,
                    'search_url': search_url
                })
            else:
                print(f"    ⚠️  No valid search URL found in results")
                results.append({
                    'company_name': company_name,
                    'search_url': None
                })
        
        # Save progress every 50 companies to avoid data loss
        if idx % 50 == 0 and len(results) > 0:
            df_results = pd.DataFrame(results)
            df_results.columns = ['name', 'url']
            df_results.to_csv(output_path, index=False)
            print(f"    💾 Progress saved ({idx}/{total})")

        # Delay between requests
        if idx < total:
            time.sleep(DEFAULT_DELAY)

    # Write final results to CSV
    print(f"\n💾 Writing final results to {output_path}...")
    df_results = pd.DataFrame(results)
    df_results.columns = ['name', 'url']
    df_results.to_csv(output_path, index=False)

    # Print summary
    successful = df_results['url'].notna().sum()
    print(f"\n✅ Complete!")
    print(f"   Total companies: {total}")
    print(f"   Successful: {successful}")
    print(f"   Failed: {total - successful}")
    print(f"   Results saved to: {output_path}")


if __name__ == "__main__":
    main()

