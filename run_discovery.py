#!/usr/bin/env python3
"""
Automated Discovery Script for ATS Platforms
Runs SearXNG, SerpAPI, and Firecrawl discovery for specified platforms
and saves results to temporary files for review.
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Import discovery modules
try:
    from searxng_discovery import discover_platform as searxng_discover
except ImportError:
    searxng_discover = None

try:
    from serpapi_discovery import discover_platform as serpapi_discover
except ImportError:
    serpapi_discover = None

try:
    from firecrawl_discovery import discover_platform as firecrawl_discover
except ImportError:
    firecrawl_discover = None

# Default platforms to discover
DEFAULT_PLATFORMS = ["lever", "workday", "workable", "smartrecruiters"]

# Create temp directory
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)


def generate_temp_filename(platform: str, method: str) -> str:
    """Generate temporary filename with timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{platform}_{method}_discovery_{timestamp}.csv"
    return str(TEMP_DIR / filename)


def run_searxng_discovery(
    platform: str, max_queries: int = 10, pages_per_query: int = 5
) -> Optional[str]:
    """Run SearXNG discovery for a platform"""
    if searxng_discover is None:
        print("⚠️  SearXNG discovery module not available")
        return None

    print("\n" + "=" * 80)
    print(f"🔍 Starting SearXNG discovery for {platform}")
    print("=" * 80)

    temp_file = generate_temp_filename(platform, "searxng")

    try:
        searxng_discover(
            platform_name=platform,
            max_queries=max_queries,
            pages_per_query=pages_per_query,
            output_file=temp_file,
        )
        print(f"✅ SearXNG discovery completed: {temp_file}")
        return temp_file
    except Exception as e:
        print(f"❌ SearXNG discovery failed for {platform}: {e}")
        return None


def run_serpapi_discovery(
    platform: str, pages_per_strategy: int = 5, max_strategies: int = 5
) -> Optional[str]:
    """Run SerpAPI discovery for a platform"""
    if serpapi_discover is None:
        print("⚠️  SerpAPI discovery module not available")
        return None

    print("\n" + "=" * 80)
    print(f"🔍 Starting SerpAPI discovery for {platform}")
    print("=" * 80)

    temp_file = generate_temp_filename(platform, "serpapi")

    try:
        serpapi_discover(
            platform_name=platform,
            pages_per_strategy=pages_per_strategy,
            max_strategies=max_strategies,
            output_file=temp_file,
        )
        print(f"✅ SerpAPI discovery completed: {temp_file}")
        return temp_file
    except Exception as e:
        print(f"❌ SerpAPI discovery failed for {platform}: {e}")
        return None


def run_firecrawl_discovery(
    platform: str, max_queries: int = 10, max_results_per_query: int = 20
) -> Optional[str]:
    """Run Firecrawl discovery for a platform"""
    if firecrawl_discover is None:
        print("⚠️  Firecrawl discovery module not available")
        return None

    print("\n" + "=" * 80)
    print(f"🔍 Starting Firecrawl discovery for {platform}")
    print("=" * 80)

    temp_file = generate_temp_filename(platform, "firecrawl")

    try:
        firecrawl_discover(
            platform_name=platform,
            max_queries=max_queries,
            max_results_per_query=max_results_per_query,
            output_file=temp_file,
        )
        print(f"✅ Firecrawl discovery completed: {temp_file}")
        return temp_file
    except Exception as e:
        print(f"❌ Firecrawl discovery failed for {platform}: {e}")
        return None


def run_all_discovery(
    platforms: List[str],
    searxng_queries: int = 10,
    searxng_pages: int = 5,
    serpapi_pages: int = 5,
    serpapi_strategies: int = 5,
    firecrawl_queries: int = 10,
    firecrawl_results: int = 20,
):
    """
    Run all discovery methods for specified platforms

    Args:
        platforms: List of platform names to discover
        searxng_queries: Max queries for SearXNG
        searxng_pages: Pages per query for SearXNG
        serpapi_pages: Pages per strategy for SerpAPI
        serpapi_strategies: Max strategies for SerpAPI
        firecrawl_queries: Max queries for Firecrawl
        firecrawl_results: Max results per query for Firecrawl
    """
    print("=" * 80)
    print("🚀 Automated Discovery for ATS Platforms")
    print("=" * 80)
    print(f"Platforms: {', '.join(platforms)}")
    print(f"Temp directory: {TEMP_DIR.absolute()}")
    print("=" * 80)

    results = {}

    for platform in platforms:
        print(f"\n{'='*80}")
        print(f"📦 Processing platform: {platform.upper()}")
        print(f"{'='*80}")

        platform_results = {}

        # Run SearXNG discovery
        searxng_file = run_searxng_discovery(
            platform, max_queries=searxng_queries, pages_per_query=searxng_pages
        )
        if searxng_file:
            platform_results["searxng"] = searxng_file
        time.sleep(2)  # Delay between methods

        # Run SerpAPI discovery
        serpapi_file = run_serpapi_discovery(
            platform,
            pages_per_strategy=serpapi_pages,
            max_strategies=serpapi_strategies,
        )
        if serpapi_file:
            platform_results["serpapi"] = serpapi_file
        time.sleep(2)  # Delay between methods

        # Run Firecrawl discovery
        firecrawl_file = run_firecrawl_discovery(
            platform,
            max_queries=firecrawl_queries,
            max_results_per_query=firecrawl_results,
        )
        if firecrawl_file:
            platform_results["firecrawl"] = firecrawl_file

        results[platform] = platform_results

        # Delay between platforms
        if platform != platforms[-1]:
            print(f"\n⏳ Waiting 5 seconds before next platform...")
            time.sleep(5)

    # Print summary
    print("\n" + "=" * 80)
    print("📊 Discovery Summary")
    print("=" * 80)

    for platform, platform_results in results.items():
        print(f"\n{platform.upper()}:")
        if not platform_results:
            print("  ⚠️  No results (all methods failed or unavailable)")
        else:
            for method, filepath in platform_results.items():
                file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                print(f"  ✅ {method}: {filepath} ({file_size:,} bytes)")

    print(f"\n✅ All discovery completed!")
    print(f"📁 Results saved in: {TEMP_DIR.absolute()}")
    print("=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Run automated discovery for ATS platforms using multiple methods"
    )
    parser.add_argument(
        "--platforms",
        nargs="+",
        choices=["lever", "workday", "workable", "smartrecruiters"],
        default=DEFAULT_PLATFORMS,
        help=f"Platforms to discover (default: {', '.join(DEFAULT_PLATFORMS)})",
    )
    parser.add_argument(
        "--searxng-queries",
        type=int,
        default=10,
        help="Max queries for SearXNG (default: 10)",
    )
    parser.add_argument(
        "--searxng-pages",
        type=int,
        default=5,
        help="Pages per query for SearXNG (default: 5)",
    )
    parser.add_argument(
        "--serpapi-pages",
        type=int,
        default=5,
        help="Pages per strategy for SerpAPI (default: 5)",
    )
    parser.add_argument(
        "--serpapi-strategies",
        type=int,
        default=5,
        help="Max strategies for SerpAPI (default: 5)",
    )
    parser.add_argument(
        "--firecrawl-queries",
        type=int,
        default=10,
        help="Max queries for Firecrawl (default: 10)",
    )
    parser.add_argument(
        "--firecrawl-results",
        type=int,
        default=20,
        help="Max results per query for Firecrawl (default: 20)",
    )

    args = parser.parse_args()

    run_all_discovery(
        platforms=args.platforms,
        searxng_queries=args.searxng_queries,
        searxng_pages=args.searxng_pages,
        serpapi_pages=args.serpapi_pages,
        serpapi_strategies=args.serpapi_strategies,
        firecrawl_queries=args.firecrawl_queries,
        firecrawl_results=args.firecrawl_results,
    )


if __name__ == "__main__":
    main()
