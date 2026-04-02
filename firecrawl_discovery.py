"""
Firecrawl-Based Company Discovery
Uses Firecrawl Search API to discover companies on ATS platforms.

Requirements:
- Firecrawl API key in .env: FIRECRAWL_API_KEY
- firecrawl-py package installed
"""

import os
import pandas as pd
import re
import time
from typing import Set, List
from dotenv import load_dotenv

try:
    from firecrawl import FirecrawlApp
except ImportError:
    FirecrawlApp = None

load_dotenv()

# Platform configurations (same as searxng_discovery.py)
PLATFORMS = {
    "lever": {
        "domains": ["jobs.lever.co"],
        "pattern": r"(https://jobs\.lever\.co/[^/?#]+)",
        "csv_column": "lever_url",
        "output_file": "lever/lever_companies.csv",
    },
    "workable": {
        "domains": ["apply.workable.com", "jobs.workable.com"],
        "pattern": [
            r"(https://apply\.workable\.com/[^/?#]+)",
            r"(https://jobs\.workable\.com/company/[^/?#]+/[^/?#]+)",
        ],
        "csv_column": "workable_url",
        "output_file": "workable/workable_companies.csv",
    },
    "smartrecruiters": {
        "domains": ["jobs.smartrecruiters.com"],
        "pattern": r"(https://jobs\.smartrecruiters\.com/[^/?#]+)",
        "csv_column": "smartrecruiters_url",
        "output_file": "smartrecruiters/smartrecruiters_companies.csv",
    },
    "workday": {
        "domains": ["myworkdayjobs.com"],
        "pattern": r"(https://[^/?#]+\.myworkdayjobs\.com/[^/?#]+)",
        "csv_column": "workday_url",
        "output_file": "workday/workday_companies.csv",
    },
}

# Search query strategies (subset of searxng strategies for efficiency)
SEARCH_STRATEGIES = [
    lambda domain: f"site:{domain}",
    lambda domain: f"site:{domain} careers",
    lambda domain: f"site:{domain} jobs",
    lambda domain: f"site:{domain} hiring",
    lambda domain: f"site:{domain} software engineer",
    lambda domain: f"site:{domain} data scientist",
    lambda domain: f"site:{domain} remote",
    lambda domain: f'site:{domain} "San Francisco"',
    lambda domain: f'site:{domain} "New York"',
    lambda domain: f'site:{domain} "London"',
    lambda domain: f"site:{domain} startup",
    lambda domain: f'site:{domain} YC OR "Y Combinator"',
]


def normalize_url(url: str) -> str:
    """Normalize URLs for case-insensitive comparisons"""
    if not isinstance(url, str):
        return ""
    return url.strip().rstrip("/").lower()


def standardize_workday_url(url: str) -> str:
    """Standardize Workday URLs to extract the company base URL"""
    if not isinstance(url, str):
        return ""

    url = url.strip().rstrip("/").lower()

    workday_pattern = r"^(https://[^/?#]+\.myworkdayjobs\.com/[^/?#]+)(?:/job/.*)?$"
    match = re.match(workday_pattern, url)

    if match:
        base_url = match.group(1)
        return base_url.rstrip("/")

    return url


def extract_company_name_from_url(url: str, platform_key: str) -> str:
    """Extract company name from URL by extracting slug and formatting it"""
    from urllib.parse import urlparse, unquote

    parsed = urlparse(url)
    path = parsed.path.lstrip("/")

    if platform_key == "lever":
        slug = path
    elif platform_key == "workable":
        slug = path
    elif platform_key == "smartrecruiters":
        slug = path.split("/")[0] if path else "unknown"
    elif platform_key == "workday":
        netloc = parsed.netloc.lower()
        if ".myworkdayjobs.com" in netloc:
            slug = netloc.split(".")[0]
        else:
            slug = "unknown"
    else:
        slug = path.split("/")[0] if path else "unknown"

    decoded = unquote(slug)
    spaced = decoded.replace("-", " ").replace("_", " ")
    return spaced.title()


def read_existing_urls(
    csv_file: str, column_name: str, platform_key: str = None
) -> Set[str]:
    """Read existing URLs from CSV file"""
    existing_urls: Set[str] = set()
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            urls_to_process = []
            if "url" in df.columns:
                urls_to_process = df["url"].dropna().tolist()
            elif column_name in df.columns:
                urls_to_process = df[column_name].dropna().tolist()

            if platform_key == "workday":
                urls_to_process = [
                    standardize_workday_url(url) for url in urls_to_process
                ]

            existing_urls = {
                normalize_url(url) for url in urls_to_process if normalize_url(url)
            }

            print(f"📖 Found {len(existing_urls)} existing URLs in {csv_file}")
        except Exception as e:
            print(f"⚠️  Error reading {csv_file}: {e}")
    return existing_urls


def extract_urls_from_results(
    results: List[dict], pattern: str | List[str], domains: List[str]
) -> Set[str]:
    """Extract company URLs from Firecrawl search results"""
    urls = set()

    if not results:
        return urls

    for result in results:
        url = result.get("url", "") or result.get("link", "")

        if not url:
            continue

        if not any(domain in url for domain in domains):
            continue

        patterns = [pattern] if isinstance(pattern, str) else pattern

        for pat in patterns:
            match = re.match(pat, url)
            if match:
                urls.add(match.group(1))
                break

    return urls


def search_firecrawl(
    app: FirecrawlApp,
    query: str,
    max_results: int = 20,
    max_retries: int = 3,
) -> List[dict]:
    """
    Perform search using Firecrawl Search API

    Args:
        app: FirecrawlApp instance
        query: Search query
        max_results: Maximum number of results to return
        max_retries: Maximum number of retries for failed requests

    Returns:
        List of search results
    """
    for attempt in range(max_retries):
        try:
            # Firecrawl search API
            response = app.search(query=query, limit=max_results)

            if isinstance(response, dict):
                results = response.get("data", []) or response.get("results", [])
            elif isinstance(response, list):
                results = response
            else:
                results = []

            return results[:max_results]

        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                print(
                    f"  ⏳ Error querying Firecrawl, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)
                continue
            else:
                print(f"  ⚠️  Error querying Firecrawl: {e}")
                return []

    return []


def save_discovered_urls(
    combined_urls: Set[str],
    platform_key: str,
    config: dict,
) -> None:
    """Save discovered URLs to CSV file with name and url columns"""
    if platform_key == "workday":
        sorted_urls = []
        for norm_url in sorted(combined_urls):
            standardized = standardize_workday_url(norm_url)
            if standardized:
                sorted_urls.append(standardized)
        sorted_urls = sorted(set(sorted_urls))
    else:
        sorted_urls = sorted(combined_urls)

    existing_data = {}
    if os.path.exists(config["output_file"]):
        try:
            df_existing = pd.read_csv(config["output_file"])
            if "url" in df_existing.columns and "name" in df_existing.columns:
                for _, row in df_existing.iterrows():
                    if pd.notna(row.get("url")):
                        url = row["url"]
                        if platform_key == "workday":
                            url = standardize_workday_url(url)
                        existing_data[url] = row.get("name", "")
        except Exception:
            pass

    rows = []
    for url in sorted_urls:
        if url in existing_data and existing_data[url]:
            name = existing_data[url]
        else:
            name = extract_company_name_from_url(url, platform_key)
        rows.append({"name": name, "url": url})

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(config["output_file"]) or ".", exist_ok=True)
    df.to_csv(config["output_file"], index=False)
    print(f"  💾 Saved {len(df)} companies to {config['output_file']}")


def discover_platform(
    platform_name: str,
    max_queries: int = 10,
    max_results_per_query: int = 20,
    output_file: str = None,
):
    """
    Discover companies using Firecrawl Search API

    Args:
        platform_name: Platform to discover
        max_queries: Maximum search queries to use
        max_results_per_query: Maximum results per query
        output_file: Optional custom output file path
    """

    if FirecrawlApp is None:
        print("❌ firecrawl-py package not installed. Install with: pip install firecrawl-py")
        return

    platform_key = platform_name.lower()

    if platform_key not in PLATFORMS:
        print(f"❌ Unknown platform: {platform_name}")
        print(f"Available platforms: {', '.join(PLATFORMS.keys())}")
        return

    config = PLATFORMS[platform_key].copy()
    if output_file:
        config["output_file"] = output_file

    print("=" * 80)
    print(f"🔍 Firecrawl Discovery: {platform_key.upper()}")
    print(f"📊 Max queries: {max_queries}")
    print(f"📊 Max results per query: {max_results_per_query}")
    print("=" * 80)

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        print("\n❌ FIRECRAWL_API_KEY not found in environment")
        print("Add to .env file: FIRECRAWL_API_KEY=your_key")
        return

    try:
        app = FirecrawlApp(api_key=api_key)
    except Exception as e:
        print(f"\n❌ Failed to initialize Firecrawl client: {e}")
        return

    # Test connection
    print(f"\n🔗 Testing Firecrawl connection...")
    test_results = search_firecrawl(app, "test", max_results=5, max_retries=2)
    if not test_results:
        print("⚠️  Warning: Test query returned no results, but continuing...")

    existing_urls = read_existing_urls(
        config["output_file"], config["csv_column"], platform_key
    )

    discovered_norms = set()
    new_urls: Set[str] = set()
    queries_used = 0
    total_results_fetched = 0

    strategies_to_use = (
        SEARCH_STRATEGIES if max_queries == -1 else SEARCH_STRATEGIES[:max_queries]
    )

    for strategy_idx, strategy_func in enumerate(strategies_to_use, 1):
        if max_queries != -1 and queries_used >= max_queries:
            print(f"\n⚠️  Reached query limit ({max_queries})")
            break

        query = strategy_func(config["domains"][0])
        print(f"\n[Query {queries_used + 1}/{max_queries if max_queries != -1 else 'unlimited'}] {query}")

        try:
            results = search_firecrawl(
                app, query, max_results=max_results_per_query, max_retries=3
            )

            total_results_fetched += len(results)

            if not results:
                print(f"  No results returned")
                queries_used += 1
                time.sleep(1)
                continue

            page_urls = extract_urls_from_results(
                results, config["pattern"], config["domains"]
            )

            if platform_key == "workday":
                page_urls = [standardize_workday_url(url) for url in page_urls]

            normalized_page_urls = {
                normalize_url(url) for url in page_urls if normalize_url(url)
            }

            new_in_query = normalized_page_urls - discovered_norms
            discovered_norms.update(normalized_page_urls)

            new_candidates = normalized_page_urls - existing_urls - new_urls
            new_urls.update(new_candidates)

            print(
                f"  Results: {len(results)} total, {len(page_urls)} relevant URLs (+{len(new_in_query)} new)"
            )

            queries_used += 1

            # Save progress after each query
            combined_urls = existing_urls.union(new_urls)
            save_discovered_urls(combined_urls, platform_key, config)
            existing_urls = combined_urls.copy()

            # Delay between queries
            time.sleep(1)

        except Exception as e:
            print(f"  ⚠️  Error on query: {e}")
            queries_used += 1
            continue

    print("\n📊 Discovery Summary:")
    print(f"  🔍 Queries used: {queries_used}")
    print(f"  📄 Total results fetched: {total_results_fetched}")
    new_count = len(new_urls)
    print(f"  🔍 Companies found: {len(discovered_norms)}")
    print(f"  🆕 New companies: {new_count}")

    combined_urls = existing_urls.union(new_urls)

    if new_count:
        print("\n🎉 Sample of new URLs (first 10):")
        for url in sorted(new_urls)[:10]:
            print(f"  ✨ {url}")
        if new_count > 10:
            print(f"  ... and {new_count - 10} more")

    save_discovered_urls(combined_urls, platform_key, config)
    print(
        f"\n✅ Final save complete: {len(combined_urls)} total companies saved to {config['output_file']}"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Firecrawl-based company discovery"
    )
    parser.add_argument(
        "--platform",
        type=str.lower,
        choices=list(PLATFORMS.keys()),
        required=True,
        help="Platform to discover",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=10,
        help="Maximum queries to use (default: 10)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum results per query (default: 20)",
    )

    args = parser.parse_args()

    discover_platform(
        args.platform,
        max_queries=args.max_queries,
        max_results_per_query=args.max_results,
    )
