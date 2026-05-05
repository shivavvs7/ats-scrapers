"""
SearXNG-Based Company Discovery
Self-hosted search alternative with no API limits.

Advantages:
- Self-hosted control
- No API limits or rate limiting
- No API keys needed
- Privacy-focused
- Aggregates results from multiple search engines
- No usage tracking

Requirements:
- SearXNG instance running (see SEARXNG_SETUP.md)
- SEARXNG_URL in .env pointing to your instance
"""

import requests
import pandas as pd
import re
import os
import shutil
import tempfile
import json
from typing import Set, List, Dict, Optional, Tuple
from dotenv import load_dotenv
from collections import defaultdict
import time
from bs4 import BeautifulSoup
from pathlib import Path

load_dotenv()

DEFAULT_ENGINES = (
    os.getenv("SEARXNG_ENGINES", "google,bing,wikipedia").strip()
    or "google,bing,wikipedia"
)

PRIMARY_ENGINE = DEFAULT_ENGINES.split(",")[0].strip() or "google"

try:
    DEFAULT_REQUEST_DELAY = float(os.getenv("SEARXNG_REQUEST_DELAY", "1.0"))
except (TypeError, ValueError):
    DEFAULT_REQUEST_DELAY = 1.0

# Platform configurations
PLATFORMS = {
    "rippling": {
        "domains": ["ats.rippling.com"],
        "pattern": r"(https://ats\.rippling\.com/[^/?#]+/jobs)",
        "csv_column": "rippling_url",
        "output_file": "rippling/rippling_companies.csv",
    },
    "ashby": {
        "domains": ["jobs.ashbyhq.com"],
        "pattern": r"(https://jobs\.ashbyhq\.com/[^/?#]+)",
        "csv_column": "ashby_url",
        "output_file": "ashby/ashby_companies.csv",
    },
    "greenhouse": {
        "domains": ["job-boards.greenhouse.io", "boards.greenhouse.io"],
        "pattern": r"(https://(?:job-boards|boards)\.greenhouse\.io/[^/?#]+)",
        "csv_column": "greenhouse_url",
        "output_file": "greenhouse/greenhouse_companies.csv",
    },
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
    "gem": {
        "domains": ["jobs.gem.com"],
        "pattern": r"(https://jobs\.gem\.com/[^/?#]+)",
        "csv_column": "gem_url",
        "output_file": "gem/gem_companies.csv",
    },
    "oracle": {
        "domains": ["oraclecloud.com"],
        "pattern": r"(https://[^/?#]+\.fa\.[^/?#]+\.oraclecloud\.com)",
        "csv_column": "oracle_url",
        "output_file": "oracle/oracle_companies.csv",
    },
    "avature": {
        "domains": ["avature.net"],
        "pattern": r"(https://[^/?#]+\.avature\.net/careers)",
        "csv_column": "avature_url",
        "output_file": "avature/avature_companies.csv",
    },
}

SEARCH_STRATEGIES = [
    # Basic site search
    lambda domain: f"site:{domain}",
    lambda domain: f"site:{domain} careers",
    lambda domain: f"site:{domain} jobs",
    lambda domain: f"site:{domain} hiring",
    lambda domain: f'site:{domain} "we\'re hiring"',
    lambda domain: f"site:{domain} apply now",
    # High-value job roles (people willing to pay)
    lambda domain: f"site:{domain} software engineer",
    lambda domain: f"site:{domain} ai engineer",
    lambda domain: f"site:{domain} machine learning",
    lambda domain: f"site:{domain} data scientist",
    lambda domain: f"site:{domain} data engineer",
    lambda domain: f"site:{domain} devops",
    lambda domain: f"site:{domain} cloud engineer",
    lambda domain: f"site:{domain} security engineer",
    lambda domain: f"site:{domain} product manager",
    lambda domain: f"site:{domain} designer",
    lambda domain: f"site:{domain} sales",
    lambda domain: f"site:{domain} enterprise sales",
    lambda domain: f"site:{domain} account executive",
    lambda domain: f"site:{domain} marketing",
    lambda domain: f"site:{domain} finance",
    lambda domain: f"site:{domain} quant",
    lambda domain: f"site:{domain} trading",
    lambda domain: f"site:{domain} fintech",
    lambda domain: f'site:{domain} "engineering"',
    lambda domain: f'site:{domain} "product"',
    lambda domain: f'site:{domain} "data"',
    # Remote
    lambda domain: f"site:{domain} remote",
    # --- Rich Countries / Wealthy Cities ---
    # Europe Tier 1
    lambda domain: f'site:{domain} "Switzerland"',
    lambda domain: f'site:{domain} "Zurich"',
    lambda domain: f'site:{domain} "Geneva"',
    lambda domain: f'site:{domain} "Luxembourg"',
    lambda domain: f'site:{domain} "Monaco"',
    lambda domain: f'site:{domain} "Norway"',
    lambda domain: f'site:{domain} "Oslo"',
    lambda domain: f'site:{domain} "Denmark"',
    lambda domain: f'site:{domain} "Copenhagen"',
    lambda domain: f'site:{domain} "Sweden"',
    lambda domain: f'site:{domain} "Stockholm"',
    # Middle East wealthy hubs
    lambda domain: f'site:{domain} "Dubai"',
    lambda domain: f'site:{domain} "Abu Dhabi"',
    lambda domain: f'site:{domain} "Saudi Arabia"',
    lambda domain: f'site:{domain} "Riyadh"',
    lambda domain: f'site:{domain} "Qatar"',
    lambda domain: f'site:{domain} "Doha"',
    lambda domain: f'site:{domain} "Kuwait"',
    lambda domain: f'site:{domain} "Bahrain"',
    # Asia rich hubs
    lambda domain: f'site:{domain} "Singapore"',
    lambda domain: f'site:{domain} "Tokyo"',
    lambda domain: f'site:{domain} "Seoul"',
    lambda domain: f'site:{domain} "Hong Kong"',
    # North America rich hubs
    lambda domain: f'site:{domain} "San Francisco"',
    lambda domain: f'site:{domain} "Silicon Valley"',
    lambda domain: f'site:{domain} "Palo Alto"',
    lambda domain: f'site:{domain} "Seattle"',
    lambda domain: f'site:{domain} "New York"',
    lambda domain: f'site:{domain} "Toronto"',
    lambda domain: f'site:{domain} "Vancouver"',
    lambda domain: f'site:{domain} "Montreal"',
    # Australia rich hubs
    lambda domain: f'site:{domain} "Sydney"',
    lambda domain: f'site:{domain} "Melbourne"',
    # Regions
    lambda domain: f'site:{domain} "Middle East"',
    lambda domain: f'site:{domain} "Europe"',
    lambda domain: f'site:{domain} "North America"',
    lambda domain: f'site:{domain} "Asia"',
    # --- Startup / VC searches ---
    lambda domain: f"site:{domain} startup",
    lambda domain: f'site:{domain} YC OR "Y Combinator"',
    # Top VCs (A16Z ++)
    lambda domain: f'site:{domain} "a16z"',
    lambda domain: f'site:{domain} "Andreessen Horowitz"',
    lambda domain: f'site:{domain} "Sequoia Capital"',
    lambda domain: f'site:{domain} "Accel"',
    lambda domain: f'site:{domain} "Index Ventures"',
    lambda domain: f'site:{domain} "Benchmark"',
    lambda domain: f'site:{domain} "Greylock"',
    lambda domain: f'site:{domain} "Lightspeed"',
    lambda domain: f'site:{domain} "Founders Fund"',
    lambda domain: f'site:{domain} "Khosla Ventures"',
    lambda domain: f'site:{domain} "Tiger Global"',
    lambda domain: f"site:{domain} series A OR series B",
    lambda domain: f'site:{domain} "tech startup"',
    # --- Big Tech / Big Corp Searches ---
    # FAANG + BigTech patterns
    lambda domain: f"site:{domain} Google",
    lambda domain: f"site:{domain} Meta",
    lambda domain: f"site:{domain} Amazon",
    lambda domain: f"site:{domain} Apple",
    lambda domain: f"site:{domain} Microsoft",
    lambda domain: f"site:{domain} Netflix",
    lambda domain: f"site:{domain} Tesla",
    # Enterprise keywords
    lambda domain: f'site:{domain} "enterprise"',
    lambda domain: f'site:{domain} "corporate"',
    lambda domain: f'site:{domain} "global careers"',
    lambda domain: f'site:{domain} "fortune 500"',
    lambda domain: f'site:{domain} "multinational"',
    lambda domain: f'site:{domain} "global offices"',
    lambda domain: f'site:{domain} "corporate jobs"',
    # Combined high-paying patterns
    lambda domain: f'site:{domain} "San Francisco" software engineer',
    lambda domain: f'site:{domain} "New York" quant',
    lambda domain: f'site:{domain} "London" fintech',
    lambda domain: f'site:{domain} "Dubai" software engineer',
    lambda domain: f'site:{domain} "Singapore" ai engineer',
    lambda domain: f'site:{domain} "Zurich" finance',
    lambda domain: f'site:{domain} "Hong Kong" trading',
    lambda domain: f"site:{domain} remote",
    lambda domain: f'site:{domain} "San Francisco"',
    lambda domain: f'site:{domain} "New York"',
    lambda domain: f'site:{domain} "London"',
    lambda domain: f'site:{domain} "Paris"',
    lambda domain: f'site:{domain} "Berlin"',
    lambda domain: f'site:{domain} "Amsterdam"',
    lambda domain: f'site:{domain} "Stockholm"',
    lambda domain: f'site:{domain} "Warsaw"',
    lambda domain: f'site:{domain} "Brussels"',
    lambda domain: f'site:{domain} "Zurich"',
    lambda domain: f'site:{domain} "Delhi"',
    lambda domain: f'site:{domain} "Mumbai"',
    lambda domain: f'site:{domain} "Bangalore"',
    lambda domain: f'site:{domain} "Chennai"',
    lambda domain: f'site:{domain} "Hyderabad"',
    lambda domain: f'site:{domain} "Pune"',
    lambda domain: f'site:{domain} "Kolkata"',
    lambda domain: f'site:{domain} "Jaipur"',
    lambda domain: f'site:{domain} "Singapore"',
    lambda domain: f'site:{domain} "Dubai"',
    lambda domain: f'site:{domain} "Tokyo"',
    lambda domain: f'site:{domain} "Seoul"',
    lambda domain: f'site:{domain} "Hong Kong"',
    lambda domain: f'site:{domain} "Toronto"',
    lambda domain: f'site:{domain} "Montreal"',
    lambda domain: f'site:{domain} "Vancouver"',
    lambda domain: f'site:{domain} "Sydney"',
    lambda domain: f'site:{domain} "Europe"',
    lambda domain: f'site:{domain} "Asia"',
    lambda domain: f'site:{domain} "Middle East"',
    lambda domain: f'site:{domain} "North America"',
    lambda domain: f'site:{domain} "South America"',
]


def load_healthy_instances(
    json_path: str = "z_searxng_instances.json",
) -> List[Dict[str, any]]:
    """
    Load healthy SearXNG instances from JSON file

    Filter criteria:
    - http.status_code == 200
    - version is recent (2026.x or 2025.x)
    - timing.search.success_percentage >= 80 (if available)

    Returns:
        List of dicts with: {url, version, timing_score}
    """
    if not os.path.exists(json_path):
        print(f"⚠️  Instance file not found: {json_path}")
        return []

    try:
        with open(json_path, "r") as f:
            data = json.load(f)

        instances_data = data.get("instances", {})
        healthy_instances = []

        for url, info in instances_data.items():
            # Check HTTP status
            http_info = info.get("http", {})
            if http_info.get("status_code") != 200:
                continue

            # Check version (2026.x or 2025.x)
            version = info.get("version", "")
            if not (version.startswith("2026.") or version.startswith("2025.")):
                continue

            # Check search success percentage if available
            timing = info.get("timing", {})
            search_timing = timing.get("search", {})
            success_pct = search_timing.get("success_percentage", 100)

            if success_pct < 80:
                continue

            # Calculate timing score (lower is better)
            # Use median search time if available, otherwise default to 5.0
            search_all = search_timing.get("all", {})
            timing_score = search_all.get("median", 5.0)

            healthy_instances.append(
                {
                    "url": url.rstrip("/"),
                    "version": version,
                    "timing_score": timing_score,
                    "success_percentage": success_pct,
                }
            )

        # Sort by timing score (fastest first)
        healthy_instances.sort(key=lambda x: x["timing_score"])

        print(f"✅ Loaded {len(healthy_instances)} healthy SearXNG instances")
        return healthy_instances

    except Exception as e:
        print(f"⚠️  Error loading instances from {json_path}: {e}")
        return []


class AdaptiveInstanceManager:
    """
    Manages SearXNG instance rotation with adaptive selection

    Features:
    - Tracks usage per instance to distribute load
    - Tracks errors to avoid problematic instances
    - Enforces cooldown periods between requests to same instance
    - Prefers local instance when available
    """

    def __init__(
        self,
        cloud_instances: List[Dict[str, any]],
        local_url: Optional[str] = None,
        min_cooldown: float = 30.0,
    ):
        self.cloud_instances = cloud_instances
        self.local_url = local_url.rstrip("/") if local_url else None
        self.min_cooldown = min_cooldown

        # Track usage and errors
        self.usage_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.last_used = {}  # url -> timestamp

        # Track if local instance is working
        self.local_working = True
        self.local_consecutive_errors = 0

    def get_next_instance(self) -> str:
        """
        Get next instance using adaptive strategy

        Returns:
            URL of the next instance to use
        """
        current_time = time.time()

        # Try local instance first if available and working
        if self.local_url and self.local_working:
            # Check cooldown
            last_use = self.last_used.get(self.local_url, 0)
            if current_time - last_use >= self.min_cooldown:
                return self.local_url

        # Select cloud instance
        if not self.cloud_instances:
            # Fallback to local even if not working
            if self.local_url:
                return self.local_url
            raise RuntimeError("No SearXNG instances available")

        # Filter instances that have cooled down
        available = []
        for instance in self.cloud_instances:
            url = instance["url"]
            last_use = self.last_used.get(url, 0)

            if current_time - last_use >= self.min_cooldown:
                # Calculate score: lower is better
                # Factors: usage count, error rate, timing
                usage = self.usage_counts[url]
                errors = self.error_counts[url]
                error_rate = errors / max(usage, 1)
                timing = instance["timing_score"]

                # Score formula: prioritize low usage, low errors, fast timing
                score = usage * 10 + error_rate * 100 + timing

                available.append((score, url))

        if not available:
            # No instances have cooled down, pick least recently used
            oldest_time = float("inf")
            oldest_url = None

            for instance in self.cloud_instances:
                url = instance["url"]
                last_use = self.last_used.get(url, 0)
                if last_use < oldest_time:
                    oldest_time = last_use
                    oldest_url = url

            if oldest_url:
                return oldest_url

            # Last resort: pick first instance
            return self.cloud_instances[0]["url"]

        # Sort by score and pick best
        available.sort(key=lambda x: x[0])
        return available[0][1]

    def record_success(self, url: str):
        """Record successful query to an instance"""
        self.usage_counts[url] += 1
        self.last_used[url] = time.time()

        # Reset local error counter on success
        if url == self.local_url:
            self.local_consecutive_errors = 0
            self.local_working = True

    def record_error(self, url: str):
        """Record failed query to an instance"""
        self.usage_counts[url] += 1
        self.error_counts[url] += 1
        self.last_used[url] = time.time()

        # Track local instance errors
        if url == self.local_url:
            self.local_consecutive_errors += 1
            # Disable local after 3 consecutive errors
            if self.local_consecutive_errors >= 3:
                self.local_working = False
                print(
                    f"  ⚠️  Local instance disabled after {self.local_consecutive_errors} consecutive errors"
                )

    def get_stats(self) -> Dict[str, any]:
        """Get usage statistics"""
        return {
            "total_requests": sum(self.usage_counts.values()),
            "total_errors": sum(self.error_counts.values()),
            "instances_used": len(self.usage_counts),
            "local_working": self.local_working if self.local_url else None,
        }


def normalize_url(url: str) -> str:
    """Normalize URLs for case-insensitive comparisons"""
    if not isinstance(url, str):
        return ""
    return url.strip().rstrip("/").lower()


def standardize_rippling_url(url: str) -> str:
    """Standardize Rippling URLs to always have /jobs format"""
    if not isinstance(url, str):
        return ""

    url = url.strip().rstrip("/").lower()

    # Match rippling URLs
    rippling_pattern = r"^https://ats\.rippling\.com/([^/?#]+)(?:/jobs)?$"
    match = re.match(rippling_pattern, url)

    if match:
        slug = match.group(1)
        return f"https://ats.rippling.com/{slug}/jobs"

    return url


def standardize_gem_url(url: str) -> str:
    """Standardize Gem URLs to extract just the company base URL"""
    if not isinstance(url, str):
        return ""

    url = url.strip().rstrip("/").lower()

    # Match Gem URLs - extract company slug only
    # Matches both company pages (jobs.gem.com/company) and job pages (jobs.gem.com/company/job-id)
    gem_pattern = r"^https://jobs\.gem\.com/([^/?#]+)"
    match = re.match(gem_pattern, url)

    if match:
        company_slug = match.group(1)
        return f"https://jobs.gem.com/{company_slug}"

    return url


def standardize_workday_url(url: str) -> str:
    """Standardize Workday URLs to extract the company base URL"""
    if not isinstance(url, str):
        return ""

    url = url.strip().rstrip("/").lower()

    # Match Workday URLs - extract company and site name (before /job/ if present)
    # Examples:
    # - https://mastercard.wd1.myworkdayjobs.com/CorporateCareers/job/...
    #   -> https://mastercard.wd1.myworkdayjobs.com/CorporateCareers
    # - https://company.wd2.myworkdayjobs.com/JobSiteName
    #   -> https://company.wd2.myworkdayjobs.com/JobSiteName
    workday_pattern = r"^(https://[^/?#]+\.myworkdayjobs\.com/[^/?#]+)(?:/job/.*)?$"
    match = re.match(workday_pattern, url)

    if match:
        # Extract the base URL (subdomain + first path segment)
        base_url = match.group(1)
        # Remove trailing slash if present
        return base_url.rstrip("/")

    return url


def standardize_oracle_url(url: str) -> str:
    """
    Standardize Oracle HCM Cloud URLs to extract base URL.
    Pattern: https://{subdomain}.fa.{region}.oraclecloud.com
    """
    if not isinstance(url, str):
        return ""

    url = url.strip().rstrip("/").lower()
    oracle_pattern = r"^(https://[^/?#]+\.fa\.[^/?#]+\.oraclecloud\.com)"
    match = re.match(oracle_pattern, url)

    if match:
        return match.group(1)

    return url


def standardize_avature_url(url: str) -> str:
    """
    Standardize Avature URLs to extract base careers URL.
    Pattern: https://{company}.avature.net/careers
    """
    if not isinstance(url, str):
        return ""

    url = url.strip().rstrip("/").lower()
    # Match base careers URL or full careers path
    avature_pattern = r"^(https://[^/?#]+\.avature\.net)(?:/careers)?"
    match = re.match(avature_pattern, url)

    if match:
        return f"{match.group(1)}/careers"

    return url


def create_temp_copy(source_path: str) -> str | None:
    """
    Create a temporary copy of the given file in the same directory.
    Returns the path to the copy, or None if copying fails.
    """
    temp_path = None
    try:
        temp_dir = os.path.dirname(source_path) or "."
        suffix = os.path.splitext(source_path)[1] or ".tmp"
        fd, temp_path = tempfile.mkstemp(prefix=".copy_", suffix=suffix, dir=temp_dir)
        os.close(fd)
        shutil.copy2(source_path, temp_path)
        return temp_path
    except OSError as e:
        print(f"⚠️  Failed to create temp copy for {source_path}: {e}")
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return None


def write_dataframe_atomically(df: pd.DataFrame, target_path: str) -> None:
    """Write DataFrame to CSV via temp file and atomically replace the original."""
    target_dir = os.path.dirname(target_path) or "."
    os.makedirs(target_dir, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".csv", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as tmp_file:
            df.to_csv(tmp_file, index=False)
        os.replace(temp_path, target_path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def extract_company_name_from_url(url: str, platform_key: str) -> str:
    """Extract company name from URL by extracting slug and formatting it"""
    from urllib.parse import urlparse, unquote

    parsed = urlparse(url)
    path = parsed.path.lstrip("/")

    if platform_key == "rippling":
        # https://ats.rippling.com/{slug}/jobs
        slug = path.split("/")[0] if path else "unknown"
    elif platform_key == "ashby":
        # https://jobs.ashbyhq.com/{slug}
        slug = path
    elif platform_key == "greenhouse":
        # https://job-boards.greenhouse.io/{slug}
        slug = path
    elif platform_key == "lever":
        # https://jobs.lever.co/{slug}
        slug = path
    elif platform_key == "workable":
        # https://apply.workable.com/{slug}
        slug = path
    elif platform_key == "smartrecruiters":
        # https://jobs.smartrecruiters.com/{company}/...
        slug = path.split("/")[0] if path else "unknown"
    elif platform_key == "workday":
        # https://{company}.wd*.myworkdayjobs.com/...
        # Extract company name from subdomain
        netloc = parsed.netloc.lower()
        if ".myworkdayjobs.com" in netloc:
            slug = netloc.split(".")[0]
        else:
            slug = "unknown"
    elif platform_key == "gem":
        # https://jobs.gem.com/{slug}
        slug = path.split("/")[0] if path else "unknown"
    elif platform_key == "oracle":
        # https://{subdomain}.fa.{region}.oraclecloud.com
        netloc = parsed.netloc.lower()
        if ".fa." in netloc and ".oraclecloud.com" in netloc:
            slug = netloc.split(".fa.")[0]
        else:
            slug = "unknown"
    elif platform_key == "avature":
        # https://{company}.avature.net/careers
        netloc = parsed.netloc.lower()
        if ".avature.net" in netloc:
            slug = netloc.split(".avature.net")[0]
        else:
            slug = "unknown"
    else:
        slug = path.split("/")[0] if path else "unknown"

    # Format slug as name: replace hyphens with spaces and title case
    decoded = unquote(slug)
    spaced = decoded.replace("-", " ").replace("_", " ")
    return spaced.title()


def enrich_oracle_names(csv_path: str) -> None:
    """
    Enrich Oracle company names by scraping actual names from careers pages.
    Only processes new entries that haven't been enriched yet.
    """
    try:
        # Import here to avoid circular dependencies
        import subprocess

        # Run enrichment script
        script_path = Path(__file__).parent / "oracle" / "enrich_company_names.py"
        if script_path.exists():
            print(f"  🔄 Enriching Oracle company names...")
            subprocess.run(
                ["python", str(script_path), "--csv", csv_path, "--delay", "1.5"],
                capture_output=True,
                text=True,
                timeout=300
            )
    except Exception as e:
        print(f"  ⚠️  Failed to enrich Oracle names: {e}")


def save_discovered_urls(
    combined_urls: Set[str],
    platform_key: str,
    config: dict,
) -> None:
    """
    Save discovered URLs to CSV file with name and url columns.
    Called after each query to preserve progress.
    """
    # Convert normalized URLs back to standardized format for platforms that need it
    if platform_key == "rippling":
        sorted_urls = []
        for norm_url in sorted(combined_urls):
            standardized = standardize_rippling_url(norm_url)
            if standardized:
                sorted_urls.append(standardized)
        sorted_urls = sorted(set(sorted_urls))
    elif platform_key == "gem":
        sorted_urls = []
        for norm_url in sorted(combined_urls):
            standardized = standardize_gem_url(norm_url)
            if standardized:
                sorted_urls.append(standardized)
        sorted_urls = sorted(set(sorted_urls))
    elif platform_key == "workday":
        sorted_urls = []
        for norm_url in sorted(combined_urls):
            standardized = standardize_workday_url(norm_url)
            if standardized:
                sorted_urls.append(standardized)
        sorted_urls = sorted(set(sorted_urls))
    elif platform_key == "oracle":
        sorted_urls = []
        for norm_url in sorted(combined_urls):
            standardized = standardize_oracle_url(norm_url)
            if standardized:
                sorted_urls.append(standardized)
        sorted_urls = sorted(set(sorted_urls))
    elif platform_key == "avature":
        sorted_urls = []
        for norm_url in sorted(combined_urls):
            standardized = standardize_avature_url(norm_url)
            if standardized:
                sorted_urls.append(standardized)
        sorted_urls = sorted(set(sorted_urls))
    else:
        sorted_urls = sorted(combined_urls)

    # Read existing data to preserve names if they exist
    existing_data = {}
    if os.path.exists(config["output_file"]):
        try:
            df_existing = pd.read_csv(config["output_file"])
            if "url" in df_existing.columns and "name" in df_existing.columns:
                for _, row in df_existing.iterrows():
                    if pd.notna(row.get("url")):
                        url = row["url"]
                        # Standardize URL to match the format we'll use as keys
                        if platform_key == "rippling":
                            url = standardize_rippling_url(url)
                        elif platform_key == "gem":
                            url = standardize_gem_url(url)
                        elif platform_key == "workday":
                            url = standardize_workday_url(url)
                        elif platform_key == "oracle":
                            url = standardize_oracle_url(url)
                        elif platform_key == "avature":
                            url = standardize_avature_url(url)
                        existing_data[url] = row.get("name", "")
        except Exception:
            pass

    # Create DataFrame with name and url columns
    rows = []
    for url in sorted_urls:
        # Use existing name if available, otherwise generate from URL
        if url in existing_data and existing_data[url]:
            name = existing_data[url]
        else:
            name = extract_company_name_from_url(url, platform_key)
        rows.append({"name": name, "url": url})

    df = pd.DataFrame(rows)
    write_dataframe_atomically(df, config["output_file"])
    print(f"  💾 Saved {len(df)} companies to {config['output_file']}")

    # Enrich Oracle company names after saving
    if platform_key == "oracle":
        enrich_oracle_names(config["output_file"])


def read_existing_urls(
    csv_file: str, column_name: str, platform_key: str = None
) -> Set[str]:
    """Read existing URLs from CSV file"""
    existing_urls: Set[str] = set()
    temp_copy = None
    if os.path.exists(csv_file):
        try:
            temp_copy = create_temp_copy(csv_file)
            read_path = temp_copy or csv_file
            df = pd.read_csv(read_path)
            urls_to_process = []
            # New format: name,url
            if "url" in df.columns:
                urls_to_process = df["url"].dropna().tolist()
            # Legacy format: specific column name
            elif column_name in df.columns:
                urls_to_process = df[column_name].dropna().tolist()

            # Standardize platform URLs before normalization
            if platform_key == "rippling":
                urls_to_process = [
                    standardize_rippling_url(url) for url in urls_to_process
                ]
            elif platform_key == "gem":
                urls_to_process = [standardize_gem_url(url) for url in urls_to_process]
            elif platform_key == "workday":
                urls_to_process = [
                    standardize_workday_url(url) for url in urls_to_process
                ]
            elif platform_key == "oracle":
                urls_to_process = [standardize_oracle_url(url) for url in urls_to_process]
            elif platform_key == "avature":
                urls_to_process = [standardize_avature_url(url) for url in urls_to_process]

            existing_urls = {
                normalize_url(url) for url in urls_to_process if normalize_url(url)
            }

            print(f"📖 Found {len(existing_urls)} existing URLs in {csv_file}")
        except Exception as e:
            print(f"⚠️  Error reading {csv_file}: {e}")
        finally:
            if temp_copy and os.path.exists(temp_copy):
                try:
                    os.remove(temp_copy)
                except OSError:
                    pass
    return existing_urls


def parse_html_results(html_content: str) -> List[dict]:
    """
    Parse HTML search results from SearXNG

    Returns list of dicts with 'url' and 'title' keys
    """
    results = []

    try:
        soup = BeautifulSoup(html_content, "html.parser")

        # Find all result articles
        # SearXNG uses <article class="result"> for each result
        articles = soup.find_all("article", class_="result")

        for article in articles:
            # Find the main link (h3 > a or direct a with result-url class)
            link = (
                article.find("a", class_="url_wrapper") or article.find("h3").find("a")
                if article.find("h3")
                else None
            )

            if link and link.get("href"):
                url = link.get("href")
                title = link.get_text(strip=True) if link.get_text(strip=True) else url

                results.append(
                    {
                        "url": url,
                        "title": title,
                    }
                )

    except Exception as e:
        # If HTML parsing fails, return empty list
        pass

    return results


def extract_urls_from_results(
    results: List[dict], pattern: str | List[str], domains: List[str]
) -> Set[str]:
    """Extract company URLs from SearXNG search results"""
    urls = set()

    if not results:
        return urls

    for result in results:
        url = result.get("url", "")

        if not url:
            continue

        # Check if URL contains target domain
        if not any(domain in url for domain in domains):
            continue

        # Handle single pattern or list of patterns
        patterns = [pattern] if isinstance(pattern, str) else pattern

        for pat in patterns:
            match = re.match(pat, url)
            if match:
                urls.add(match.group(1))
                break

    return urls


def search_searxng(
    searxng_url: str,
    query: str,
    page: int = 1,
    engines: str = PRIMARY_ENGINE,
    max_retries: int = 3,
    use_html: bool = True,
) -> List[dict]:
    """
    Perform search using SearXNG instance with retry logic for rate limiting

    Tries HTML format first (less rate-limited), falls back to JSON if needed

    Args:
        searxng_url: Base URL of SearXNG instance (e.g., http://localhost:8080)
        query: Search query
        page: Page number (default: 1)
        engines: Comma-separated list of search engines to use
        max_retries: Maximum number of retries for rate-limited requests
        use_html: Try HTML format first (default: True)

    Returns:
        List of search results
    """
    endpoint = f"{searxng_url.rstrip('/')}/search"

    # Browser-like headers to avoid rate limiting
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": searxng_url,
    }

    # Try HTML first (less rate-limited on public instances)
    if use_html:
        params_html = {
            "q": query,
            "pageno": page,
            "language": "en",
            "safesearch": 0,
        }
        if engines:
            params_html["engines"] = engines

        headers_html = headers.copy()
        headers_html["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        )

        try:
            response = requests.get(
                endpoint, params=params_html, headers=headers_html, timeout=30
            )

            if response.status_code == 200:
                # Parse HTML results
                results = parse_html_results(response.text)
                if results:
                    return results
                # If HTML parsing failed or no results, fall through to JSON
            elif response.status_code != 429:
                # For non-429 errors, fall through to JSON
                pass
        except Exception:
            # If HTML request fails, fall through to JSON
            pass

    # Fall back to JSON API (or use directly if use_html=False)
    params = {
        "q": query,
        "format": "json",
        "pageno": page,
        "engines": engines,
        "language": "en",
        "safesearch": 0,
    }

    headers_json = headers.copy()
    headers_json["Accept"] = "application/json"

    for attempt in range(max_retries):
        try:
            response = requests.get(
                endpoint, params=params, headers=headers_json, timeout=30
            )

            # Handle rate limiting (429) with exponential backoff
            if response.status_code == 429:
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    print(
                        f"  ⏳ Rate limited (429), retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    print(
                        f"  ⚠️  Rate limited (429) after {max_retries} attempts, skipping this query"
                    )
                    return []

            response.raise_for_status()
            data = response.json()

            # Check for engine errors in the response
            errors = data.get("errors", [])
            if errors and len(errors) > 3:
                print(f"    ⚠️  {len(errors)} engine errors occurred")

            results = data.get("results", [])
            return results

        except requests.exceptions.RequestException as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                print(
                    f"  ⏳ Rate limited, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)
                continue
            elif attempt == max_retries - 1:
                return []
            else:
                return []
        except Exception as e:
            return []

    return []


def discover_platform(
    platform_name: str,
    max_queries: int = 20,
    pages_per_query: int = 20,
    engines: str = DEFAULT_ENGINES,
    request_delay: float = DEFAULT_REQUEST_DELAY,
    output_file: str = None,
    use_cloud: bool = None,
    local_only: bool = False,
    min_instance_cooldown: float = 30.0,
):
    """
    Discover companies using SearXNG

    Args:
        platform_name: Platform to discover
        max_queries: Maximum search queries to use (default: unlimited)
        pages_per_query: Pages per query (default: 3)
        engines: Search engines to use (default pulled from SEARXNG_ENGINES)
        request_delay: Seconds to wait between page fetches
        output_file: Optional custom output file path (overrides config default)
        use_cloud: Enable cloud instances (default: from env SEARXNG_USE_CLOUD)
        local_only: Use only local instance (default: False)
        min_instance_cooldown: Minimum seconds between requests to same instance
    """

    platform_key = platform_name.lower()

    if platform_key not in PLATFORMS:
        print(f"❌ Unknown platform: {platform_name}")
        print(f"Available platforms: {', '.join(PLATFORMS.keys())}")
        return

    config = PLATFORMS[platform_key].copy()
    if output_file:
        config["output_file"] = output_file

    print("=" * 80)
    print(f"🔍 SearXNG Discovery: {platform_key.upper()}")
    print(f"📊 Max queries: {max_queries}")
    print(f"📊 Pages per query: {pages_per_query}")
    print(f"🔧 Engines: {engines}")
    print(f"⏱️ Delay between page requests: {request_delay}s")
    print("=" * 80)

    query_cooldown = max(request_delay, 1.0)

    # Determine if we should use cloud instances
    if use_cloud is None:
        use_cloud_env = os.getenv("SEARXNG_USE_CLOUD", "false").lower()
        use_cloud = use_cloud_env in ("true", "1", "yes")

    # Get local instance URL
    local_url = os.getenv("SEARXNG_URL") if not local_only else os.getenv("SEARXNG_URL")

    # Load cloud instances if enabled
    cloud_instances = []
    if use_cloud and not local_only:
        instances_file = os.getenv("SEARXNG_INSTANCES_FILE", "z_searxng_instances.json")
        cloud_instances = load_healthy_instances(instances_file)
        if cloud_instances:
            print(f"🌐 Loaded {len(cloud_instances)} cloud instances")

    # Check if we have at least one instance available
    if not local_url and not cloud_instances:
        print("\n❌ No SearXNG instances available")
        print("\nOptions:")
        print("1. Set SEARXNG_URL in .env for local instance")
        print("2. Enable cloud instances with --use-cloud flag")
        print("3. Ensure z_searxng_instances.json exists for cloud instances")
        return

    # Initialize instance manager
    instance_manager = AdaptiveInstanceManager(
        cloud_instances=cloud_instances,
        local_url=local_url,
        min_cooldown=min_instance_cooldown,
    )

    # Test connection with first available instance
    print(f"\n🔗 Testing connection...")
    test_instance = instance_manager.get_next_instance()
    print(f"   Using: {test_instance}")
    test_results = search_searxng(
        test_instance, "test", page=1, engines=engines, max_retries=5
    )
    if not test_results:
        print("⚠️  Test query returned no results, but continuing...")
        instance_manager.record_error(test_instance)
    else:
        print(f"✅ Connected! Got {len(test_results)} test results")
        instance_manager.record_success(test_instance)

    # Read existing URLs
    existing_urls = read_existing_urls(
        config["output_file"], config["csv_column"], platform_key
    )

    discovered_norms = set()
    new_urls: Set[str] = set()
    queries_used = 0
    total_results_fetched = 0
    instance_usage_log = []  # Track which instances were used

    # Use search strategies
    strategies_to_use = (
        SEARCH_STRATEGIES if max_queries == -1 else SEARCH_STRATEGIES[:max_queries]
    )

    for strategy_idx, strategy_func in enumerate(strategies_to_use, 1):
        if max_queries != -1 and queries_used >= max_queries:
            print(
                f"\n⚠️  Reached query limit ({max_queries if max_queries != -1 else 'unlimited'})"
            )
            break

        query = strategy_func(config["domains"][0])
        print(
            f"\n[Query {queries_used + 1}/{max_queries if max_queries != -1 else 'unlimited'}] {query}"
        )

        query_norms = set()

        for page in range(1, pages_per_query + 1):
            try:
                # Get next instance from manager
                current_instance = instance_manager.get_next_instance()
                instance_usage_log.append(current_instance)

                # Show which instance we're using (only for cloud instances or if verbose)
                if current_instance != local_url or not local_url:
                    instance_display = current_instance.replace("https://", "").replace(
                        "http://", ""
                    )
                    if len(instance_display) > 40:
                        instance_display = instance_display[:37] + "..."
                    print(f"  📡 Using: {instance_display}")

                # SearXNG search with selected instance
                results = search_searxng(
                    current_instance, query, page=page, engines=engines
                )

                if results:
                    instance_manager.record_success(current_instance)
                    total_results_fetched += len(results)
                else:
                    instance_manager.record_error(current_instance)
                    print(f"  Page {page}: No results returned")
                    if page == 1:
                        # Try with fallback engine
                        print(f"    💡 Retrying with {PRIMARY_ENGINE} as fallback...")
                        fallback_results = search_searxng(
                            current_instance, query, page=page, engines=PRIMARY_ENGINE
                        )
                        if fallback_results:
                            print(
                                f"    ✅ Got {len(fallback_results)} results with {PRIMARY_ENGINE}"
                            )
                            results = fallback_results
                            total_results_fetched += len(fallback_results)
                            instance_manager.record_success(current_instance)
                        else:
                            print(
                                f"    ⚠️  {PRIMARY_ENGINE} fallback also returned no results"
                            )
                            break
                    else:
                        break

                # Extract URLs
                page_urls = extract_urls_from_results(
                    results, config["pattern"], config["domains"]
                )

                # Standardize platform URLs
                if platform_key == "rippling":
                    page_urls = [standardize_rippling_url(url) for url in page_urls]
                elif platform_key == "gem":
                    page_urls = [standardize_gem_url(url) for url in page_urls]
                elif platform_key == "workday":
                    page_urls = [standardize_workday_url(url) for url in page_urls]
                elif platform_key == "oracle":
                    page_urls = [standardize_oracle_url(url) for url in page_urls]
                elif platform_key == "avature":
                    page_urls = [standardize_avature_url(url) for url in page_urls]

                normalized_page_urls = {
                    normalize_url(url) for url in page_urls if normalize_url(url)
                }

                # Calculate truly new URLs (not in CSV, not discovered this session)
                truly_new = normalized_page_urls - existing_urls - new_urls
                new_urls.update(truly_new)

                # Track all discovered URLs for this query
                query_norms.update(normalized_page_urls)

                # Show only truly new URLs
                if truly_new:
                    print(
                        f"  Page {page}: {len(results)} results, +{len(truly_new)} NEW URLs"
                    )
                    # Show first 5 new URLs
                    for url in sorted(truly_new)[:5]:
                        print(f"    ✨ {url}")
                    if len(truly_new) > 5:
                        print(f"    ... and {len(truly_new) - 5} more new URLs")
                else:
                    print(
                        f"  Page {page}: {len(results)} results, 0 new URLs (all already known)"
                    )

                # Delay to avoid rate limiting (configurable via CLI/env)
                if request_delay > 0:
                    time.sleep(request_delay)

            except Exception as e:
                print(f"  ⚠️  Error on page {page}: {e}")
                if "current_instance" in locals():
                    instance_manager.record_error(current_instance)
                break

        queries_used += 1
        new_from_query = query_norms - discovered_norms
        discovered_norms.update(query_norms)

        print(f"  Query summary: +{len(new_from_query)} URLs found this query")

        # Save progress after each query to preserve work if script is stopped
        combined_urls = existing_urls.union(new_urls)
        save_discovered_urls(combined_urls, platform_key, config)

        # Update existing_urls to include newly discovered URLs for next iteration
        # This ensures we don't duplicate work and the save reflects current state
        existing_urls = combined_urls.copy()

        # Delay between queries to avoid rate limiting
        if strategy_idx < len(strategies_to_use) and query_cooldown > 0:
            time.sleep(query_cooldown)

    # Get instance manager stats
    manager_stats = instance_manager.get_stats()

    print("\n📊 Discovery Summary:")
    print(f"  🔍 Queries used: {queries_used}")
    print(f"  🌐 Instances used: {len(set(instance_usage_log))}")
    print(f"  📄 Total results fetched: {total_results_fetched}")
    print(f"  🆕 NEW companies discovered: {len(new_urls)}")
    print(f"  📚 Previously known: {len(existing_urls) - len(new_urls)}")
    print(f"  📊 Total after discovery: {len(existing_urls)}")

    # Show instance stats
    if manager_stats["total_requests"] > 0:
        error_rate = (
            manager_stats["total_errors"] / manager_stats["total_requests"]
        ) * 100
        print(f"\n📈 Instance Stats:")
        print(f"  Total requests: {manager_stats['total_requests']}")
        print(f"  Total errors: {manager_stats['total_errors']} ({error_rate:.1f}%)")
        print(f"  Unique instances: {manager_stats['instances_used']}")

    # Final save (data is already saved after each query, but save once more to ensure consistency)
    combined_urls = existing_urls

    if new_urls:
        print(f"\n🎉 All {len(new_urls)} newly discovered URLs:")
        for url in sorted(new_urls):
            print(f"  ✨ {url}")
    else:
        print("\nℹ️  No new URLs discovered (all URLs were already in the CSV)")

    # Final save using helper function
    save_discovered_urls(combined_urls, platform_key, config)
    print(
        f"\n✅ Final save complete: {len(combined_urls)} total companies in {config['output_file']}"
    )


def discover_all_platforms(
    max_queries_per_platform: int = -1,
    pages_per_query: int = 20,
    engines: str = DEFAULT_ENGINES,
    request_delay: float = DEFAULT_REQUEST_DELAY,
    use_cloud: bool = None,
    local_only: bool = False,
    min_instance_cooldown: float = 30.0,
):
    """Discover all platforms using SearXNG"""

    print("=" * 80)
    print("🔍 SearXNG Discovery - All Platforms")
    print(f"📊 Queries per platform: {max_queries_per_platform}")
    print(f"📊 Pages per query: {pages_per_query}")
    print(f"🔧 Engines: {engines}")
    print(f"⏱️ Delay between page requests: {request_delay}s")
    print(f"🌐 Cloud instances: {'enabled' if use_cloud else 'disabled'}")
    print(f"🏠 Local only: {local_only}")
    print("=" * 80)

    platform_cooldown = max(5.0, request_delay * 4)

    for platform_name in PLATFORMS.keys():
        print("\n" + "=" * 80)
        discover_platform(
            platform_name,
            max_queries=max_queries_per_platform,
            pages_per_query=pages_per_query,
            engines=engines,
            request_delay=request_delay,
            use_cloud=use_cloud,
            local_only=local_only,
            min_instance_cooldown=min_instance_cooldown,
        )
        print("=" * 80)
        time.sleep(platform_cooldown)

    print("\n" + "=" * 80)
    print("✅ All platforms discovered!")
    print("=" * 80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="SearXNG-based company discovery with cloud instance support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use local instance only
  python searxng_discovery.py --platform lever --local-only
  
  # Use cloud instances only
  python searxng_discovery.py --platform workday --use-cloud
  
  # Use both local and cloud instances
  python searxng_discovery.py --platform all --use-cloud
  
  # Quick discovery with limited queries
  python searxng_discovery.py --platform ashby --max-queries 5 --pages 3 --use-cloud
        """,
    )
    parser.add_argument(
        "--platform",
        type=str.lower,
        choices=list(PLATFORMS.keys()) + ["all"],
        default="all",
        help="Platform to discover (default: all)",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=-1,
        help="Maximum queries to use (default: unlimited)",
    )
    parser.add_argument(
        "--pages", type=int, default=20, help="Pages per query (default: 20)"
    )
    parser.add_argument(
        "--engines",
        type=str,
        default=DEFAULT_ENGINES,
        help=f"Search engines to use (default: {DEFAULT_ENGINES})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
        help=f"Seconds to sleep between page requests (default: {DEFAULT_REQUEST_DELAY})",
    )
    parser.add_argument(
        "--use-cloud",
        action="store_true",
        help="Enable cloud SearXNG instances from z_searxng_instances.json",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Use only local SearXNG instance (SEARXNG_URL)",
    )
    parser.add_argument(
        "--min-cooldown",
        type=float,
        default=30.0,
        help="Minimum seconds between requests to same instance (default: 30)",
    )

    args = parser.parse_args()

    if args.platform == "all":
        discover_all_platforms(
            max_queries_per_platform=args.max_queries,
            pages_per_query=args.pages,
            engines=args.engines,
            request_delay=args.delay,
            use_cloud=args.use_cloud,
            local_only=args.local_only,
            min_instance_cooldown=args.min_cooldown,
        )
    else:
        discover_platform(
            args.platform,
            max_queries=args.max_queries,
            pages_per_query=args.pages,
            engines=args.engines,
            request_delay=args.delay,
            use_cloud=args.use_cloud,
            local_only=args.local_only,
            min_instance_cooldown=args.min_cooldown,
        )
