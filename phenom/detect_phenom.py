"""
Phenom People ATS Detection Tool

Technical fingerprinting to identify if a website uses Phenom People's
recruitment platform.

Detection Signatures:
1. API Endpoint: POST /widgets endpoint
2. Session Cookies: PLAY_SESSION, PHPPPE_ACT, VISITED_LANG, VISITED_COUNTRY
3. CSRF Token: x-csrf-token header requirement
4. HTML Markers: "powered by Phenom" footer text
5. JavaScript: phenom.com CDN references

Usage:
    python phenom/detect_phenom.py https://careers.example.com

Returns:
    Phenom detected: Yes/No
    Company code: XXXXX (if detected)
"""

import argparse
import re
import sys
from urllib.parse import urlparse

import requests


def detect_phenom(url: str, verbose: bool = False) -> dict:
    """
    Detect if a URL uses Phenom People's platform.

    Args:
        url: URL to check
        verbose: Print detailed detection info

    Returns:
        Dictionary with:
            - is_phenom: bool - Whether Phenom was detected
            - confidence: str - "high", "medium", "low", or "none"
            - signals: list - List of detected signals
            - company_code: str or None - Extracted company code if found
            - suggested_config: dict or None - Suggested configuration
    """
    if not url.startswith("http"):
        url = f"https://{url}"

    result = {
        "is_phenom": False,
        "confidence": "none",
        "signals": [],
        "company_code": None,
        "suggested_config": None
    }

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })

    # Try to load the main page
    try:
        if verbose:
            print(f"Checking {url}...")

        # Try common career page paths
        paths_to_try = [
            "/",
            "/en/us/search-results",
            "/us/en/search-results",
            "/search-results",
            "/careers",
            "/jobs"
        ]

        main_response = None
        for path in paths_to_try:
            try:
                test_url = url.rstrip("/") + path
                response = session.get(test_url, timeout=15, allow_redirects=True)
                if response.status_code == 200:
                    main_response = response
                    if verbose:
                        print(f"  ✓ Found page at {path}")
                    break
            except:
                continue

        if not main_response:
            if verbose:
                print("  ✗ Could not load any page")
            return result

        # Signal 1: Check for Phenom cookies
        cookie_signals = []
        for cookie in session.cookies:
            cookie_name = cookie.name.upper()
            if any(name in cookie_name for name in ["PLAY_SESSION", "PHPPPE_ACT", "VISITED_LANG", "VISITED_COUNTRY"]):
                cookie_signals.append(cookie.name)

        if cookie_signals:
            result["signals"].append(f"Phenom cookies: {', '.join(cookie_signals)}")
            if verbose:
                print(f"  ✓ Found Phenom cookies: {cookie_signals}")

        # Signal 2: Check HTML for Phenom markers
        html = main_response.text

        # Look for "Phenom" in HTML
        if re.search(r'phenom', html, re.IGNORECASE):
            result["signals"].append("Phenom reference in HTML")
            if verbose:
                print("  ✓ Found Phenom reference in HTML")

        # Look for phenom.com CDN
        if "phenom.com" in html.lower():
            result["signals"].append("Phenom CDN detected")
            if verbose:
                print("  ✓ Found Phenom CDN")

        # Look for specific Phenom JavaScript files
        if re.search(r'phenompeople|phenom-people', html, re.IGNORECASE):
            result["signals"].append("Phenom JavaScript detected")
            if verbose:
                print("  ✓ Found Phenom JavaScript")

        # Signal 3: Test for /widgets endpoint
        widgets_url = url.rstrip("/") + "/widgets"
        try:
            # Try a minimal POST request to /widgets
            test_payload = {
                "lang": "en",
                "deviceType": "desktop",
                "country": "us",
                "pageName": "search-results"
            }

            widgets_response = session.post(
                widgets_url,
                json=test_payload,
                timeout=10,
                headers={"Content-Type": "application/json"}
            )

            # A 400 or 200 response indicates the endpoint exists
            if widgets_response.status_code in [200, 400]:
                result["signals"].append("/widgets endpoint exists")
                if verbose:
                    print(f"  ✓ /widgets endpoint responded with {widgets_response.status_code}")

                # Try to extract error messages that might indicate Phenom
                try:
                    response_json = widgets_response.json()
                    if isinstance(response_json, dict):
                        # Look for Phenom-specific error structures
                        if any(key in response_json for key in ["refineSearch", "jobDetails", "ddoKey"]):
                            result["signals"].append("Phenom API structure detected")
                            if verbose:
                                print("  ✓ Phenom API structure detected in response")
                except:
                    pass

        except requests.exceptions.Timeout:
            if verbose:
                print("  - /widgets endpoint timed out")
        except Exception as e:
            if verbose:
                print(f"  - /widgets check failed: {e}")

        # Signal 4: Try to extract company code from HTML
        company_code = None

        # Look for company code in JavaScript variables
        # Common patterns: companyCode: "XXXXX", company_code: "XXXXX"
        code_patterns = [
            r'companyCode["\']?\s*:\s*["\']([A-Z0-9]+)["\']',
            r'company_code["\']?\s*:\s*["\']([A-Z0-9]+)["\']',
            r'COMPANY_CODE["\']?\s*:\s*["\']([A-Z0-9]+)["\']',
        ]

        for pattern in code_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                company_code = match.group(1)
                result["signals"].append(f"Company code found: {company_code}")
                if verbose:
                    print(f"  ✓ Extracted company code: {company_code}")
                break

        # Determine confidence level
        signal_count = len(result["signals"])
        if signal_count >= 3:
            result["confidence"] = "high"
            result["is_phenom"] = True
        elif signal_count == 2:
            result["confidence"] = "medium"
            result["is_phenom"] = True
        elif signal_count == 1:
            result["confidence"] = "low"
            result["is_phenom"] = True

        # Set company code if found
        if company_code:
            result["company_code"] = company_code

            # Try to suggest config
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Guess locale and country from URL
            locale = "en"
            country = "us"

            # Common patterns
            if ".ca" in domain or "/ca/" in url.lower():
                locale = "en_ca"
                country = "ca"
            elif "/uk/" in url.lower() or ".uk" in domain:
                locale = "en_uk"
                country = "uk"
            elif "global" in domain or "global" in url.lower():
                locale = "en_global"
                country = "global"

            result["suggested_config"] = {
                "url": url,
                "company_code": company_code,
                "locale": locale,
                "country": country
            }

        if verbose:
            print(f"\nConfidence: {result['confidence']}")
            print(f"Is Phenom: {result['is_phenom']}")

        return result

    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  ✗ Error: {e}")
        return result


def main():
    parser = argparse.ArgumentParser(
        description="Detect if a website uses Phenom People's recruitment platform"
    )
    parser.add_argument("url", help="URL to check")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    result = detect_phenom(args.url, verbose=args.verbose)

    print("\n" + "=" * 60)
    print("PHENOM DETECTION RESULT")
    print("=" * 60)
    print(f"URL: {args.url}")
    print(f"Phenom Detected: {'Yes' if result['is_phenom'] else 'No'}")
    print(f"Confidence: {result['confidence']}")

    if result["signals"]:
        print(f"\nDetected Signals ({len(result['signals'])}):")
        for signal in result["signals"]:
            print(f"  • {signal}")

    if result["company_code"]:
        print(f"\nCompany Code: {result['company_code']}")

    if result["suggested_config"]:
        print("\nSuggested Configuration:")
        config = result["suggested_config"]
        print(f"  URL: {config['url']}")
        print(f"  Company Code: {config['company_code']}")
        print(f"  Locale: {config['locale']}")
        print(f"  Country: {config['country']}")

        print("\nCSV Entry:")
        print(f"{config['url']},COMPANY_NAME,{config['company_code']},{config['locale']},{config['country']}")

    print("=" * 60)

    # Exit with appropriate code
    sys.exit(0 if result["is_phenom"] else 1)


if __name__ == "__main__":
    main()
