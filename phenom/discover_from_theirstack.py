"""
Discover Phenom companies from TheirStack.

TheirStack maintains a list of companies using Phenom People:
https://theirstack.com/en/technology/phenom-people

This script helps you process that list and validate each company.

Process:
1. Visit TheirStack and manually compile the company list
2. Use this script to validate and extract configs
3. Build comprehensive companies.csv

Usage:
    python phenom/discover_from_theirstack.py companies_to_check.txt
"""

import argparse
import asyncio
import csv
import sys
from pathlib import Path

# Import our detection and extraction tools
sys.path.insert(0, str(Path(__file__).resolve().parent))
from detect_phenom import detect_phenom
from extract_company_config import extract_from_browser_inspection


async def process_company(company_name: str, careers_url: str = None):
    """
    Process a single company: detect Phenom and extract config.

    Args:
        company_name: Company name
        careers_url: Known careers URL (if available)

    Returns:
        Dictionary with results or None if not Phenom
    """
    print(f"\n{'='*60}")
    print(f"Processing: {company_name}")
    print(f"{'='*60}")

    # If no URL provided, try to find it
    if not careers_url:
        # Common patterns for career sites
        domain_variants = [
            f"careers.{company_name.lower().replace(' ', '')}.com",
            f"jobs.{company_name.lower().replace(' ', '')}.com",
            f"www.{company_name.lower().replace(' ', '')}.com/careers",
        ]

        print(f"No URL provided. Trying common patterns...")
        for variant in domain_variants:
            print(f"  Trying: https://{variant}")
            try:
                result = detect_phenom(f"https://{variant}", verbose=False)
                if result["is_phenom"]:
                    careers_url = f"https://{variant}"
                    print(f"  ✓ Found Phenom site!")
                    break
            except Exception as e:
                print(f"  ✗ Failed: {e}")
                continue

        if not careers_url:
            print(f"✗ Could not find careers URL for {company_name}")
            return None

    # Detect Phenom
    print(f"\n1. Detecting Phenom at {careers_url}...")
    detection_result = detect_phenom(careers_url, verbose=True)

    if not detection_result["is_phenom"]:
        print(f"✗ {company_name} does not appear to use Phenom")
        return None

    print(f"✓ Phenom detected with {detection_result['confidence']} confidence")

    # Extract configuration
    print(f"\n2. Extracting configuration...")
    config = extract_from_browser_inspection(careers_url)

    if not config:
        print(f"✗ Could not extract configuration")
        return None

    # Check if we have company_code
    if not config.get("company_code"):
        print(f"\n⚠ WARNING: Company code not found!")
        print(f"\nManual extraction required:")
        print(f"1. Visit: {careers_url}")
        print(f"2. Open DevTools (F12) → Network tab")
        print(f"3. Search for a job")
        print(f"4. Find POST /widgets request")
        print(f"5. Look for company code in request/page source")

        company_code = input("\nEnter company code (or press Enter to skip): ").strip().upper()
        if company_code:
            config["company_code"] = company_code
        else:
            print(f"Skipping {company_name} - no company code")
            return None

    # Build result
    result = {
        "company_name": company_name,
        "url": config["base_url"],
        "company_code": config.get("company_code"),
        "locale": config.get("locale", "en"),
        "country": config.get("country", "us"),
        "confidence": detection_result["confidence"],
        "signals": len(detection_result["signals"])
    }

    print(f"\n✓ Configuration extracted:")
    print(f"  Company: {result['company_name']}")
    print(f"  URL: {result['url']}")
    print(f"  Company Code: {result['company_code']}")
    print(f"  Locale: {result['locale']}")
    print(f"  Country: {result['country']}")

    return result


async def process_company_list(input_file: str, output_csv: str = None):
    """
    Process a list of companies from a text file.

    Input file format:
        Company Name, https://careers.url.com
        Another Company, https://jobs.another.com
        Company Without URL

    Args:
        input_file: Path to input file with company list
        output_csv: Path to output CSV (default: phenom/discovered_companies.csv)
    """
    if not output_csv:
        output_csv = Path(__file__).parent / "discovered_companies.csv"

    results = []

    # Read input file
    with open(input_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Parse line: "Company Name, https://url" or just "Company Name"
            parts = [p.strip() for p in line.split(",", 1)]
            company_name = parts[0]
            careers_url = parts[1] if len(parts) > 1 else None

            print(f"\n[{line_num}] Processing: {company_name}")

            try:
                result = await process_company(company_name, careers_url)
                if result:
                    results.append(result)
                    print(f"✓ Added {company_name}")
                else:
                    print(f"✗ Skipped {company_name}")
            except Exception as e:
                print(f"✗ Error processing {company_name}: {e}")

            # Add delay to be respectful
            await asyncio.sleep(2)

    # Write results to CSV
    if results:
        print(f"\n{'='*60}")
        print(f"Writing {len(results)} companies to {output_csv}")
        print(f"{'='*60}")

        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "url", "name", "company_code", "locale", "country"
            ])
            writer.writeheader()

            for result in results:
                writer.writerow({
                    "url": result["url"],
                    "name": result["company_name"],
                    "company_code": result["company_code"],
                    "locale": result["locale"],
                    "country": result["country"]
                })

        print(f"✓ Saved to {output_csv}")
        print(f"\nNext steps:")
        print(f"1. Review {output_csv}")
        print(f"2. Manually verify company codes")
        print(f"3. Merge into phenom/companies.csv")
        print(f"4. Run: python phenom/main.py")
    else:
        print(f"\n✗ No companies discovered")


def main():
    parser = argparse.ArgumentParser(
        description="Discover Phenom companies from a list",
        epilog="""
Example input file format (companies.txt):

    # TheirStack Phenom Companies
    Gamestop, https://careers.gamestop.com
    Thomson Reuters, https://jobs.thomsonreuters.com
    Philips, https://www.careers.philips.com
    Truist Bank
    Citrix

Then run:
    python phenom/discover_from_theirstack.py companies.txt
        """
    )
    parser.add_argument(
        "input_file",
        help="Text file with company names and optional URLs"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output CSV file (default: discovered_companies.csv)"
    )
    args = parser.parse_args()

    asyncio.run(process_company_list(args.input_file, args.output))


if __name__ == "__main__":
    main()
