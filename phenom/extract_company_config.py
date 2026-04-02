"""
Phenom Company Configuration Extractor

Extracts company_code, locale, and country from Phenom-powered career sites.

Two methods:
1. Browser automation (intercepts /widgets POST request)
2. HAR file analysis (if HAR file is provided)

Usage:
    # Method 1: Automated extraction
    python phenom/extract_company_config.py https://jobs.bell.ca

    # Method 2: From HAR file
    python phenom/extract_company_config.py --har captured_traffic.har

    # Save to CSV
    python phenom/extract_company_config.py https://jobs.bell.ca --append-to-csv

Output:
    company_code: BECACA
    locale: en_ca
    country: ca
"""

import argparse
import json
import sys
import csv
from pathlib import Path
from urllib.parse import urlparse


def extract_from_har(har_file_path: str) -> dict:
    """
    Extract Phenom configuration from HAR file.

    Args:
        har_file_path: Path to HAR file

    Returns:
        Dictionary with company_code, locale, country, base_url
    """
    try:
        with open(har_file_path, "r", encoding="utf-8") as f:
            har_data = json.load(f)
    except Exception as e:
        print(f"Error loading HAR file: {e}")
        return None

    # Find /widgets POST requests in the HAR file
    for entry in har_data.get("log", {}).get("entries", []):
        request = entry.get("request", {})
        url = request.get("url", "")

        # Look for /widgets endpoint
        if "/widgets" in url and request.get("method") == "POST":
            # Extract the base URL
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"

            # Extract request payload
            post_data = request.get("postData", {})
            mime_type = post_data.get("mimeType", "")

            if "application/json" in mime_type:
                try:
                    payload = json.loads(post_data.get("text", "{}"))

                    # Extract config from payload
                    locale = payload.get("lang", "en")
                    country = payload.get("country", "us")

                    # Company code is trickier - it's not always in the payload
                    # It might be in headers, cookies, or the page URL
                    company_code = None

                    # Try to find it in headers
                    for header in request.get("headers", []):
                        if header.get("name", "").lower() == "x-company-code":
                            company_code = header.get("value")
                            break

                    # If found any info, return it
                    if locale or country:
                        return {
                            "base_url": base_url,
                            "company_code": company_code,
                            "locale": locale,
                            "country": country,
                            "source": "har"
                        }

                except json.JSONDecodeError:
                    continue

    print("Could not extract Phenom configuration from HAR file")
    return None


def extract_from_browser_inspection(url: str) -> dict:
    """
    Extract configuration by analyzing the website.

    This is a simplified version that doesn't use full browser automation.
    Instead, it makes requests and analyzes responses.

    For full browser automation, users should:
    1. Visit the career site
    2. Open DevTools (F12)
    3. Go to Network tab
    4. Search for jobs
    5. Find POST /widgets request
    6. Examine the payload

    Args:
        url: Career site URL

    Returns:
        Dictionary with extracted config (may be incomplete)
    """
    import requests

    if not url.startswith("http"):
        url = f"https://{url}"

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })

    print(f"Analyzing {url}...")
    print("\nNote: Automatic extraction is limited. For best results:")
    print("1. Visit the career site in your browser")
    print("2. Open DevTools (F12) → Network tab")
    print("3. Search for any job")
    print("4. Find POST request to /widgets")
    print("5. Check the Request Payload for:")
    print("   - lang (e.g., 'en_ca')")
    print("   - country (e.g., 'ca')")
    print("6. Look for company code in page source or cookies")

    try:
        # Try to load the search results page
        search_paths = [
            "/en/us/search-results",
            "/us/en/search-results",
            "/search-results",
        ]

        response = None
        for path in search_paths:
            try:
                test_url = url.rstrip("/") + path
                r = session.get(test_url, timeout=15, allow_redirects=True)
                if r.status_code == 200:
                    response = r
                    print(f"\n✓ Found page at {path}")
                    break
            except:
                continue

        if not response:
            print("\n✗ Could not load career page")
            return None

        # Try to extract from URL path
        parsed = urlparse(response.url)
        path_parts = parsed.path.split("/")

        # Phenom URLs often have pattern: /{country}/{lang}/search-results
        # e.g., /ca/en/search-results or /us/en/search-results
        locale = None
        country = None

        if len(path_parts) >= 3:
            # Try to identify country and locale from path
            for i, part in enumerate(path_parts):
                if part in ["ca", "us", "uk", "global"]:
                    country = part
                    # Next part might be locale
                    if i + 1 < len(path_parts) and path_parts[i + 1] in ["en", "fr", "de", "es"]:
                        locale = f"{path_parts[i + 1]}_{country}"
                        break

        # If not found in path, check cookies
        if not country:
            for cookie in session.cookies:
                if "VISITED_COUNTRY" in cookie.name:
                    country = cookie.value
                if "VISITED_LANG" in cookie.name:
                    locale = cookie.value

        # Try to extract company code from HTML
        html = response.text
        import re

        company_code = None
        code_patterns = [
            r'companyCode["\']?\s*:\s*["\']([A-Z0-9]+)["\']',
            r'company_code["\']?\s*:\s*["\']([A-Z0-9]+)["\']',
        ]

        for pattern in code_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                company_code = match.group(1)
                break

        # Default guesses
        if not locale:
            locale = "en"
        if not country:
            # Try to guess from domain
            domain = urlparse(url).netloc.lower()
            if ".ca" in domain:
                country = "ca"
                locale = "en_ca"
            elif ".uk" in domain:
                country = "uk"
                locale = "en_uk"
            else:
                country = "us"
                locale = "en_us"

        return {
            "base_url": url,
            "company_code": company_code,
            "locale": locale,
            "country": country,
            "source": "automatic",
            "confidence": "low" if not company_code else "medium"
        }

    except Exception as e:
        print(f"\n✗ Error: {e}")
        return None


def append_to_csv(config: dict, csv_path: str = None):
    """
    Append configuration to companies.csv

    Args:
        config: Configuration dictionary
        csv_path: Path to CSV file (default: phenom/companies.csv)
    """
    if not csv_path:
        script_dir = Path(__file__).parent
        csv_path = script_dir / "companies.csv"

    if not config.get("company_code"):
        print("\n✗ Cannot append to CSV: company_code is required")
        return False

    # Check if URL already exists
    existing_urls = set()
    if Path(csv_path).exists():
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_urls.add(row["url"].lower().rstrip("/"))

    url_normalized = config["base_url"].lower().rstrip("/")
    if url_normalized in existing_urls:
        print(f"\n✗ URL already exists in {csv_path}")
        return False

    # Prompt for company name
    company_name = input("\nEnter company name: ").strip()
    if not company_name:
        print("✗ Company name is required")
        return False

    # Append to CSV
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            config["base_url"],
            company_name,
            config["company_code"],
            config["locale"],
            config["country"]
        ])

    print(f"\n✓ Added to {csv_path}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Extract Phenom company configuration"
    )
    parser.add_argument(
        "url_or_har",
        nargs="?",
        help="URL to analyze or path to HAR file"
    )
    parser.add_argument(
        "--har",
        action="store_true",
        help="Treat input as HAR file path"
    )
    parser.add_argument(
        "--append-to-csv",
        action="store_true",
        help="Append extracted config to companies.csv"
    )
    args = parser.parse_args()

    if not args.url_or_har:
        parser.print_help()
        sys.exit(1)

    # Extract config
    if args.har:
        config = extract_from_har(args.url_or_har)
    else:
        config = extract_from_browser_inspection(args.url_or_har)

    if not config:
        print("\n✗ Could not extract configuration")
        sys.exit(1)

    # Display results
    print("\n" + "=" * 60)
    print("EXTRACTED CONFIGURATION")
    print("=" * 60)
    print(f"Base URL: {config.get('base_url', 'N/A')}")
    print(f"Company Code: {config.get('company_code', 'NOT FOUND')}")
    print(f"Locale: {config.get('locale', 'N/A')}")
    print(f"Country: {config.get('country', 'N/A')}")

    if config.get("confidence"):
        print(f"Confidence: {config['confidence']}")

    # Show CSV entry
    if config.get("company_code"):
        print("\nCSV Entry:")
        print(f"{config['base_url']},COMPANY_NAME,{config['company_code']},{config['locale']},{config['country']}")
    else:
        print("\n⚠ WARNING: Company code not found!")
        print("Please manually extract it from DevTools:")
        print("1. Visit the career site")
        print("2. Open DevTools → Network tab")
        print("3. Search for jobs")
        print("4. Find POST /widgets request")
        print("5. Look for company code in the request")

    print("=" * 60)

    # Optionally append to CSV
    if args.append_to_csv and config.get("company_code"):
        append_to_csv(config)


if __name__ == "__main__":
    main()
