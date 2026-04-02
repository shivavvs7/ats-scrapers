"""
Tesla Jobs Scraper - Simplified Playwright Version
"""

import json
import re
import time
import sys
from typing import Dict, List, Any
from datetime import datetime
from pathlib import Path
import logging

try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
except ImportError:
    print("ERROR: Playwright not installed. Run: pip install playwright")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "https://www.tesla.com"
API_STATE_ENDPOINT = "/cua-api/apps/careers/state"
API_JOB_DETAIL_ENDPOINT = "/cua-api/careers/job/{job_id}"
CAREERS_PAGE = "/careers/search/"
REQUEST_DELAY = 0.5


class TeslaJobsAPI:
    """Tesla API client using Playwright."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self) -> None:
        """Launch browser and navigate to Tesla careers."""
        logger.info("Launching browser...")
        self.playwright = sync_playwright().start()

        # Launch with anti-automation flags
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
            ]
        )

        self.page = self.browser.new_page()

        logger.info("Navigating to Tesla careers page...")
        self.page.goto(f"{BASE_URL}{CAREERS_PAGE}", wait_until="networkidle", timeout=60000)

        logger.info("Waiting for page to settle...")
        time.sleep(5)

        # Simulate human behavior
        self.page.evaluate("window.scrollBy(0, 300)")
        time.sleep(1)
        self.page.evaluate("window.scrollBy(0, -300)")

        logger.info("Page ready")

    def _make_request(self, url: str) -> Dict[str, Any]:
        """Make request by navigating in browser."""
        logger.debug(f"Navigating to: {url}")

        response = self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

        if response.status != 200:
            logger.error(f"Got status {response.status}")
            # Save screenshot for debugging
            try:
                self.page.screenshot(path="error_screenshot.png")
                logger.info("Screenshot saved to error_screenshot.png")
            except:
                pass
            raise Exception(f"Request failed: {response.status}")

        content = self.page.content()

        # Extract JSON
        if '<pre>' in content:
            json_match = re.search(r'<pre[^>]*>(.*?)</pre>', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))

        try:
            body_text = self.page.inner_text('body')
            return json.loads(body_text)
        except Exception as e:
            logger.error(f"Failed to parse JSON: {e}")
            raise

    def get_all_jobs(self) -> Dict[str, Any]:
        """Fetch all job listings."""
        url = f"{BASE_URL}{API_STATE_ENDPOINT}"
        data = self._make_request(url)
        logger.info(f"Fetched {len(data.get('listings', []))} job listings")
        return data

    def get_job_details(self, job_id: str) -> Dict[str, Any]:
        """Fetch job details."""
        url = f"{BASE_URL}{API_JOB_DETAIL_ENDPOINT.format(job_id=job_id)}"
        data = self._make_request(url)
        return data

    def close(self) -> None:
        """Clean up resources."""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


def load_cache(cache_file: str) -> Dict[str, Dict[str, Any]]:
    """Load cached job descriptions."""
    cache_path = Path(cache_file)
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            logger.info(f"Loaded {len(cache)} cached descriptions")
            return cache
        except Exception as e:
            logger.warning(f"Could not load cache: {e}")
            return {}
    return {}


def save_cache(cache: Dict[str, Dict[str, Any]], cache_file: str) -> None:
    """Save cache."""
    cache_path = Path(cache_file)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(cache)} descriptions to cache")


def create_job_url_slug(title: str, job_id: str) -> str:
    """Create URL slug."""
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    return f"{slug}-{job_id}"


def scrape_tesla_jobs(headless: bool = False) -> Dict[str, Any]:
    """Scrape all Tesla jobs."""
    logger.info("="*70)
    logger.info(f"TESLA JOBS SCRAPER ({'HEADLESS' if headless else 'VISIBLE'})")
    logger.info("="*70)

    # Setup cache
    script_dir = Path(__file__).parent
    cache_dir = script_dir / "cache"
    cache_dir.mkdir(exist_ok=True)
    cache_file = str(cache_dir / "job_descriptions_cache.json")

    cache = load_cache(cache_file)

    # Fetch jobs
    with TeslaJobsAPI(headless=headless) as api:
        all_data = api.get_all_jobs()
        locations = all_data.get('lookup', {}).get('locations', {})
        listings = all_data.get('listings', [])

        logger.info(f"Found {len(listings)} job listings")

        jobs_to_fetch = []
        formatted_jobs = []
        cached_count = 0

        for job in listings:
            job_id = job.get('id', '')
            title = job.get('t', '')
            location = locations.get(job.get('l', ''), 'Unknown')

            if job_id in cache:
                cached_data = cache[job_id]
                cached_count += 1
            else:
                jobs_to_fetch.append(job)
                cached_data = {}

            job_url_slug = create_job_url_slug(title, job_id)
            job_url = f"{BASE_URL}/careers/search/job/{job_url_slug}"

            formatted_job = {
                'url': job_url,
                'title': title,
                'location': location,
                'description': cached_data.get('job_description', ''),
                'id': job_id,
                'department': cached_data.get('department', ''),
                'time_type': cached_data.get('time_type', ''),
            }
            formatted_jobs.append(formatted_job)

        logger.info(f"Cached: {cached_count}, To fetch: {len(jobs_to_fetch)}")

        # Fetch missing job details
        if jobs_to_fetch:
            logger.info(f"Fetching {len(jobs_to_fetch)} job descriptions...")

            for idx, job in enumerate(jobs_to_fetch, 1):
                try:
                    job_id = job['id']
                    logger.info(f"[{idx}/{len(jobs_to_fetch)}] Fetching {job_id}...")

                    details = api.get_job_details(job_id)

                    # Extract description
                    parts = []
                    if details.get('jobDescription'):
                        parts.append(f"Description:\n{details['jobDescription']}")
                    if details.get('jobResponsibilities'):
                        parts.append(f"Responsibilities:\n{details['jobResponsibilities']}")
                    if details.get('jobRequirements'):
                        parts.append(f"Requirements:\n{details['jobRequirements']}")
                    if details.get('jobCompensationAndBenefits'):
                        parts.append(f"Compensation & Benefits:\n{details['jobCompensationAndBenefits']}")

                    job_description = '\n\n'.join(parts) if parts else ''
                    department = details.get('department', '')
                    time_type = details.get('timeType', '')

                    # Update cache
                    cache[job_id] = {
                        'job_description': job_description,
                        'department': department,
                        'time_type': time_type
                    }

                    # Update formatted job
                    for fj in formatted_jobs:
                        if fj['id'] == job_id:
                            fj['description'] = job_description
                            fj['department'] = department
                            fj['time_type'] = time_type
                            break

                    time.sleep(REQUEST_DELAY)

                    if idx % 50 == 0:
                        logger.info(f"Checkpoint: saving cache at {idx} jobs...")
                        save_cache(cache, cache_file)

                except Exception as e:
                    logger.error(f"Error fetching {job['id']}: {e}")
                    continue

            save_cache(cache, cache_file)

    output = {
        'last_scraped': datetime.now().isoformat(),
        'name': 'Tesla',
        'jobs': formatted_jobs
    }

    logger.info(f"Scraped {len(formatted_jobs)} total jobs")
    return output


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Scrape Tesla job postings")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    args = parser.parse_args()

    data = scrape_tesla_jobs(headless=args.headless)

    output_file = Path("tesla.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    file_size_mb = output_file.stat().st_size / (1024 * 1024)

    logger.info("="*70)
    logger.info("COMPLETED")
    logger.info("="*70)
    logger.info(f"Saved to: {output_file}")
    logger.info(f"File size: {file_size_mb:.1f} MB")
    logger.info(f"Total jobs: {len(data['jobs'])}")

    if data['jobs']:
        sample = data['jobs'][0]
        logger.info(f"\nSample: {sample['title']} - {sample['location']}")


if __name__ == "__main__":
    main()
