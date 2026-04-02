"""
Meta Jobs Scraper

⚠️ NOTE: As of December 2025, Meta requires login to view individual job descriptions.
This scraper can only fetch job metadata (title, location, teams, URLs) from the public
job search page via GraphQL responses.

What this scraper fetches:
- Job ID
- Job title
- Locations (all locations for each job)
- Teams and sub-teams
- Direct URL to job posting
- ~1000+ job listings in ~10-30 seconds

What it CANNOT fetch (requires login):
- Job descriptions
- Qualifications
- Responsibilities
- Other detailed job information

To get descriptions, you would need to:
1. Manually log in to Meta Careers
2. Use authenticated session cookies
3. Or use Meta's official API if available

Usage:
    python3 main.py              # Fetch all job listings (metadata only)
    python3 main.py --no-descriptions  # Same as above (explicit)

The scraper includes parallel description fetching code that is currently
non-functional due to Meta's login requirement, but kept for future use.
"""

import json
import time
from playwright.sync_api import sync_playwright
import os
from typing import Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

JOBS_PAGE_URL = "https://www.metacareers.com/jobs"
def get_description_cache_file():
    """Get the path to the description cache file"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "meta_descriptions_cache.json")

# Unwanted patterns to remove from job descriptions
UNWANTED_PATTERNS = [
    # Navigation
    "Skip to main content",
    "Jobs",
    "Teams",
    "Career Programs",
    "Working at Meta",
    "Blog",
    # Apply/Action buttons
    "Apply for this job",
    "Take the first step toward a rewarding career at Meta",
    "Apply now",
    "APPLY NOW",
    # Search/Filter
    "Find your role",
    "Explore jobs that match your skills and experience",
    "Search by technology, team or location to find an opening that's right for you",
    "View jobs",
    "Job Search",
    # Teams/Departments (header navigation)
    "Business Teams",
    "Technology Teams",
    "Program Management",
    "Engineering",
    "Product Management",
    "Data Science",
    "Design",
    "Research",
    # Working at Meta section
    "Accessiblity and Engagement",
    "Benefits",
    "Culture",
    "Hiring Process",
    # Account
    "My account",
    "Career profile",
    "Account settings",
    "Messages",
    # Blog/About
    "Meta Careers Blog",
    "About us",
    "About Meta",
    "Media gallery",
    "Brand resources",
    "For investors",
    # Footer legal
    "Community Standards",
    "Data Policy",
    "Terms",
    "Cookie Policy",
    "Report a bug",
    "Looking for contractor roles?",
    # Cookie consent
    "Accept cookies from Meta Careers on this browser",
    "We use cookies to help personalize and improve content and services",
    "serve relevant ads and provide a safer experience",
    "You can review your cookie controls at any time",
    "Learn more about cookie uses and controls in our Cookie Policy",
    "Learn More",
    "Accept All",
    # Research/Programs (common navigation items)
    "Accelerate Eng Talent",
    "Students and Grads",
    "Rotational Programs",
    # Footer accommodations and legal
    "If you need assistance or an accommodation due to a disability",
    "fill out the Accommodations request form",
    "Notice regarding automated employment decision tools in New York City",
    "If you have any trouble, you can report an issue",
]

# Patterns that indicate the end of job description content
END_PATTERNS = [
    "©2025 Meta",
    "©2024 Meta",
    "©Meta",
    "Notice regarding automated employment decision tools",
]


def clean_job_description(raw_text):
    """Clean job description by removing navigation, footer, and unwanted content"""
    if not raw_text:
        return None

    lines = raw_text.split("\n")
    cleaned_lines = []

    # Track if we've seen actual job content
    job_content_started = False
    title_seen = False

    for line in lines:
        line_stripped = line.strip()

        # Check if we've hit the end markers (copyright, footer, etc.)
        if any(pattern in line_stripped for pattern in END_PATTERNS):
            break

        # Skip empty lines at the beginning
        if not job_content_started and not line_stripped:
            continue

        # Skip unwanted patterns
        if any(
            pattern.lower() in line_stripped.lower() for pattern in UNWANTED_PATTERNS
        ):
            continue

        # Skip very short lines that are likely navigation
        if len(line_stripped) < 3:
            continue

        # Skip lines that look like "+2 more" or similar category indicators
        if line_stripped.startswith("+") and "more" in line_stripped.lower():
            continue

        # Skip lines that are just punctuation or numbers
        if all(c in "+-.,;:/()[]{}" for c in line_stripped.replace(" ", "")):
            continue

        # Skip the duplicate title at the beginning (usually appears twice)
        if not title_seen and not job_content_started:
            # First occurrence of what looks like a title
            if len(line_stripped) > 10 and len(line_stripped) < 200:
                title_seen = True
                continue

        # Skip location lines (e.g., "Sunnyvale, CA +1 location")
        if "+" in line_stripped and "location" in line_stripped.lower():
            continue

        # Skip lines that look like navigation (short, few words)
        if not job_content_started and len(line_stripped.split()) <= 3:
            # Skip single or double word lines at the beginning
            continue

        # Mark that we've started seeing real content
        # Job descriptions typically have sentences with multiple words
        if len(line_stripped) > 50 or (len(line_stripped.split()) > 8):
            job_content_started = True

        cleaned_lines.append(line)

    # Join and clean up extra whitespace
    cleaned_text = "\n".join(cleaned_lines)

    # Remove multiple consecutive newlines
    while "\n\n\n" in cleaned_text:
        cleaned_text = cleaned_text.replace("\n\n\n", "\n\n")

    # Remove leading/trailing whitespace
    cleaned_text = cleaned_text.strip()

    # Return None if cleaned text is too short (likely just navigation)
    if len(cleaned_text) < 100:
        return None

    return cleaned_text


def fetch_job_description_playwright(job_url, browser):
    """Fetch job description from individual job page using Playwright"""
    try:
        page = browser.new_page()
        page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1.5)  # Wait for content to render

        # Extract job description from the page
        raw_description = page.evaluate("""
            () => {
                // Try to find the main job content first
                const contentSelectors = [
                    '[role="main"]',
                    'main',
                    'article'
                ];

                for (const selector of contentSelectors) {
                    const element = document.querySelector(selector);
                    if (element) {
                        const text = element.innerText || element.textContent;
                        if (text && text.length > 200) {
                            return text.trim();
                        }
                    }
                }

                // Fallback: get body text
                const body = document.body;
                if (body) {
                    return body.innerText || body.textContent;
                }

                return null;
            }
        """)

        page.close()

        # Clean the description to remove navigation and footer content
        cleaned_description = clean_job_description(raw_description)
        return cleaned_description

    except Exception as e:
        print(f"  ✗ Error fetching {job_url}: {e}")
        return None


def fetch_single_description(job_data):
    """Fetch a single job description in a separate browser instance (for parallel processing)"""
    job_url = job_data.get("url")
    job_id = job_data.get("id")

    if not job_url:
        return job_id, None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            page = browser.new_page()
            page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.5)

            raw_description = page.evaluate("""
                () => {
                    const contentSelectors = [
                        '[role="main"]',
                        'main',
                        'article'
                    ];

                    for (const selector of contentSelectors) {
                        const element = document.querySelector(selector);
                        if (element) {
                            const text = element.innerText || element.textContent;
                            if (text && text.length > 200) {
                                return text.trim();
                            }
                        }
                    }

                    const body = document.body;
                    if (body) {
                        return body.innerText || body.textContent;
                    }

                    return null;
                }
            """)

            browser.close()

            cleaned_description = clean_job_description(raw_description)
            return job_id, cleaned_description

    except Exception as e:
        return job_id, None


def scrape_meta_jobs():
    """Scrape Meta jobs using Playwright for browser automation"""
    all_jobs = []
    graphql_data = []

    with sync_playwright() as p:
        print("Launching browser...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        page = context.new_page()

        # Capture GraphQL responses
        def handle_response(response):
            if "graphql" in response.url:
                try:
                    # Check if response is OK before parsing
                    if response.ok:
                        # Parse JSON immediately before browser/page closes
                        json_data = response.json()
                        if json_data:
                            graphql_data.append(json_data)
                            print(f"✓ Captured GraphQL response from {response.url}")
                except Exception as e:
                    # Only print error if it's not a "closed" error after we got data
                    if "closed" not in str(e).lower() or not graphql_data:
                        print(f"Error parsing GraphQL response: {e}")

        page.on("response", handle_response)

        print(f"Navigating to {JOBS_PAGE_URL}...")
        response = page.goto(
            JOBS_PAGE_URL, wait_until="networkidle", timeout=60000
        )

        actual_url = page.url
        print(f"Actual URL after navigation: {actual_url}")
        print(f"Response status: {response.status}")

        # Wait for GraphQL requests to complete and be processed
        print("Waiting for jobs to load...")

        # Try to wait for job elements to appear
        try:
            page.wait_for_selector('[data-testid="job-card"]', timeout=10000)
            print("Job cards detected on page")
        except Exception:
            print("No job cards detected, but continuing anyway...")

        # Scroll to trigger lazy loading
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(2)
        except Exception as e:
            print(f"Could not scroll page: {e}")

        # Give extra time for GraphQL responses to be captured
        time.sleep(5)

        print("Extracting jobs from GraphQL responses...")
        all_jobs = []

        # Process GraphQL responses if we captured any
        if graphql_data:
            print(f"\nProcessing {len(graphql_data)} GraphQL responses...")
            script_dir = os.path.dirname(os.path.abspath(__file__))
            gql_path = os.path.join(script_dir, "meta_graphql_responses.json")
            with open(gql_path, "w", encoding="utf-8") as f:
                json.dump(graphql_data, f, indent=2)
            print(f"Saved GraphQL responses to {gql_path}")

            # Try to extract jobs from GraphQL data
            for gql_response in graphql_data:
                if isinstance(gql_response, dict) and "data" in gql_response:
                    # Navigate through possible GraphQL response structures
                    data = gql_response.get("data", {})

                    # Check for job_search_with_featured_jobs structure (the one Meta uses)
                    if "job_search_with_featured_jobs" in data:
                        job_search = data["job_search_with_featured_jobs"]
                        job_results = job_search.get("all_jobs", [])

                        if job_results:
                            print(f"Found {len(job_results)} jobs in GraphQL response!")
                            for job in job_results:
                                job_id = job.get("id")
                                # Construct URL from job ID
                                job_url = (
                                    f"https://www.metacareers.com/jobs/{job_id}/"
                                    if job_id
                                    else None
                                )

                                all_jobs.append(
                                    {
                                        "id": job_id,
                                        "title": job.get("title"),
                                        "locations": job.get("locations", []),
                                        "teams": job.get("teams", []),
                                        "sub_teams": job.get("sub_teams", []),
                                        "url": job_url,
                                    }
                                )
                        continue

                    # Fallback: try other possible paths
                    job_results = (
                        data.get("job_search_results", {}).get("results", [])
                        or data.get("jobSearchResults", {}).get("results", [])
                        or data.get("careers", {}).get("jobs", [])
                        or []
                    )

                    if job_results:
                        print(f"Found {len(job_results)} jobs in GraphQL response!")
                        for job in job_results:
                            all_jobs.append(
                                {
                                    "id": job.get("id"),
                                    "title": job.get("title"),
                                    "location": job.get("location")
                                    or job.get("locations"),
                                    "team": job.get("team") or job.get("teams"),
                                    "url": job.get("posting_url") or job.get("url"),
                                    "updated_time": job.get("updated_time"),
                                }
                            )

        print(f"Total jobs extracted: {len(all_jobs)}")

        # If we didn't get any jobs, save debugging info
        if not all_jobs:
            print("\n⚠ No jobs found. Saving page content for debugging...")
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                
                # Save page HTML
                html_content = page.content()
                html_path = os.path.join(script_dir, "meta_debug_page.html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                print(f"  Saved page HTML to {html_path}")

                # Take a screenshot
                screenshot_path = os.path.join(script_dir, "meta_debug_screenshot.png")
                page.screenshot(path=screenshot_path)
                print(f"  Saved screenshot to {screenshot_path}")

                # Try to extract any visible job data directly from the page
                print("\n  Attempting direct page extraction...")
                jobs_on_page = page.evaluate("""
                    () => {
                        const jobs = [];
                        // Try multiple possible selectors for job cards
                        const selectors = [
                            '[data-testid="job-card"]',
                            '[role="listitem"]',
                            'a[href*="/jobs/"]',
                            '.job-card',
                            '[class*="job"]'
                        ];

                        for (const selector of selectors) {
                            const elements = document.querySelectorAll(selector);
                            if (elements.length > 0) {
                                console.log(`Found ${elements.length} elements with selector: ${selector}`);
                                elements.forEach(el => {
                                    const text = el.innerText || el.textContent || '';
                                    const link = el.href || el.querySelector('a')?.href || '';
                                    if (text || link) {
                                        jobs.push({ text: text.substring(0, 200), link });
                                    }
                                });
                                break;
                            }
                        }
                        return jobs;
                    }
                """)

                if jobs_on_page:
                    print(f"  Found {len(jobs_on_page)} potential job elements on page")
                    debug_jobs_path = os.path.join(script_dir, "meta_debug_jobs.json")
                    with open(debug_jobs_path, "w", encoding="utf-8") as f:
                        json.dump(jobs_on_page, f, indent=2)
                    print(f"  Saved to {debug_jobs_path}")
                else:
                    print("  No job elements found on page")

            except Exception as e:
                print(f"  Error saving debug info: {e}")

        browser.close()

    return all_jobs


def load_description_cache():
    """Load cached descriptions from file"""
    cache_file = get_description_cache_file()
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  ⚠ Warning: Could not load cache file: {e}")
            return {}
    return {}


def save_description_cache(cache):
    """Save description cache to file"""
    try:
        cache_file = get_description_cache_file()
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  ⚠ Warning: Could not save cache file: {e}")


def fetch_descriptions_for_jobs(all_jobs, limit=None, max_workers=10):
    """Fetch descriptions for all jobs using Playwright with caching and parallel processing

    Args:
        all_jobs: List of job dictionaries
        limit: Maximum number of jobs to fetch descriptions for (None = all jobs)
        max_workers: Number of parallel workers for fetching (default: 10)
    """
    jobs_to_process = all_jobs[:limit] if limit else all_jobs

    # Load cache
    cache = load_description_cache()
    cache_hits = 0
    cache_misses = 0

    print(f"\nFetching descriptions for {len(jobs_to_process)} jobs...")
    if limit and limit < len(all_jobs):
        print(f"  (Limited to first {limit} jobs out of {len(all_jobs)} total)")

    if cache:
        print(f"  Loaded cache with {len(cache)} entries")

    # Clean up stale cache entries (jobs that no longer exist)
    current_job_ids = {job.get("id") for job in all_jobs if job.get("id")}
    stale_cache_ids = set(cache.keys()) - current_job_ids

    if stale_cache_ids:
        print(f"  Removing {len(stale_cache_ids)} stale cache entries for deleted jobs...")
        for stale_id in stale_cache_ids:
            del cache[stale_id]
        save_description_cache(cache)
        print(f"  ✓ Cache cleaned, now has {len(cache)} entries")

    # First pass: use cache where possible
    jobs_needing_fetch = []
    for job in jobs_to_process:
        job_id = job.get("id")
        if job_id and job_id in cache:
            job["description"] = cache[job_id]
            cache_hits += 1
        else:
            jobs_needing_fetch.append(job)

    if cache_hits > 0:
        print(f"  ✓ Using cached descriptions for {cache_hits} jobs")

    # Second pass: fetch missing descriptions IN PARALLEL
    if jobs_needing_fetch:
        print(f"  Fetching {len(jobs_needing_fetch)} new descriptions with {max_workers} parallel workers...")
        print(f"  ⚠️  IMPORTANT: Only the CACHE is saved incrementally during fetching.")
        print(f"                meta.json will ONLY be saved at the END to prevent data corruption.")

        completed = 0
        successful = 0

        # Use ThreadPoolExecutor for parallel fetching
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all jobs
            future_to_job = {
                executor.submit(fetch_single_description, job): job
                for job in jobs_needing_fetch
            }

            # Process results as they complete
            for future in as_completed(future_to_job):
                job = future_to_job[future]
                completed += 1

                try:
                    job_id, description = future.result()

                    # Apply description to job object immediately
                    job["description"] = description

                    # Cache the description if we have a job ID
                    if job_id and description:
                        cache[job_id] = description
                        cache_misses += 1
                        successful += 1

                    # CRITICAL: Save ONLY cache incrementally, NEVER meta.json
                    # meta.json will only be saved once at the end by the caller
                    # This ensures we never have a partially-complete meta.json file
                    if cache_misses > 0 and cache_misses % 50 == 0:
                        save_description_cache(cache)
                        print(f"  💾 Auto-saved cache ({cache_misses} descriptions cached so far)")

                    # Print progress every 10 jobs or at milestones
                    if completed % 10 == 0 or completed == len(jobs_needing_fetch):
                        print(f"  Progress: {completed}/{len(jobs_needing_fetch)} fetched ({successful} with descriptions)")

                except Exception as e:
                    job["description"] = None
                    print(f"  ✗ Error processing job: {e}")

        # Save final cache update
        if cache_misses > 0:
            save_description_cache(cache)
            print(f"  ✓ Final cache save: {cache_misses} new descriptions cached")

        print(f"  ⚠️  If interrupted, re-run to resume. Cached descriptions will be reused.")

    # Set description to None for remaining jobs if limited
    if limit:
        for job in all_jobs[limit:]:
            job["description"] = None

    print(
        f"  ✓ Completed fetching descriptions (Cache: {cache_hits} hits, {cache_misses} misses)"
    )
    return all_jobs


def save_jobs(all_jobs, filename="meta.json"):
    """Save jobs to JSON file in standardized format"""
    wrapped = {
        "last_scraped": datetime.now().isoformat(),
        "name": "Meta",
        "jobs": all_jobs,
    }

    # Save to the script's directory, not current working directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(wrapped, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved {len(all_jobs)} jobs to {filepath}")


def load_jobs(filename="meta.json"):
    """Load jobs from JSON file"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, filename)

    if not os.path.exists(filepath):
        print(f"⚠ File {filepath} does not exist")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    print(f"✓ Loaded {len(jobs)} jobs from {filepath}")
    return jobs


def main(fetch_descriptions=True, description_limit=None):
    """
    Main function to scrape Meta jobs

    Args:
        fetch_descriptions: Whether to fetch job descriptions (default: True)
        description_limit: Maximum number of descriptions to fetch (None = all)
    """
    # Step 1: Fetch job listings (without descriptions)
    print("=" * 60)
    print("STEP 1: Fetching job listings...")
    print("=" * 60)
    all_jobs = scrape_meta_jobs()

    print(f"\n✓ Total jobs fetched: {len(all_jobs)}")

    # Step 2: Save jobs immediately (without descriptions)
    print("\n" + "=" * 60)
    print("STEP 2: Saving job listings (without descriptions)...")
    print("=" * 60)
    save_jobs(all_jobs, "meta.json")
    print("  ✓ Safe to interrupt - job listings are saved!")

    # Step 3: Fetch descriptions if requested
    if all_jobs and fetch_descriptions:
        print("\n" + "=" * 60)
        print("STEP 3: Fetching job descriptions...")
        print("=" * 60)
        print("  NOTE: Cache is auto-saved every 50 descriptions.")
        print("        If interrupted, descriptions will resume from cache on next run.")
        print("        meta.json will NOT be updated until all descriptions are fetched.\n")

        all_jobs = fetch_descriptions_for_jobs(all_jobs, limit=description_limit)

        # IMPORTANT: Only save meta.json AFTER all descriptions are fetched
        print("\n" + "=" * 60)
        print("STEP 4: Saving final results with descriptions...")
        print("=" * 60)
        save_jobs(all_jobs, "meta.json")
        print("  ✓ All jobs with descriptions saved to meta.json")

    print("\n" + "=" * 60)
    print("✓ COMPLETE!")
    print("=" * 60)
    return all_jobs


def fetch_descriptions_only(input_file="meta.json", output_file="meta.json", limit=None, max_workers=10):
    """
    Standalone function to fetch descriptions for already-scraped jobs

    This is useful if you want to:
    - Fetch descriptions separately after getting job listings
    - Re-fetch descriptions for jobs that failed
    - Add descriptions to an existing jobs file

    Args:
        input_file: JSON file with job listings
        output_file: Where to save jobs with descriptions
        limit: Maximum number of descriptions to fetch (None = all)
        max_workers: Number of parallel workers (default: 10)
    """
    print("=" * 60)
    print(f"Loading jobs from {input_file}...")
    print("=" * 60)

    jobs = load_jobs(input_file)

    if not jobs:
        print("⚠ No jobs found to process")
        return []

    print("\n" + "=" * 60)
    print("Fetching descriptions...")
    print("=" * 60)
    print("  NOTE: Cache is auto-saved every 50 descriptions.")
    print("        If interrupted, run this function again to resume from cache.")
    print(f"        {output_file} will NOT be updated until all descriptions are fetched.\n")

    jobs = fetch_descriptions_for_jobs(jobs, limit=limit, max_workers=max_workers)

    # IMPORTANT: Only save output file AFTER all descriptions are fetched
    print("\n" + "=" * 60)
    print(f"Saving final results to {output_file}...")
    print("=" * 60)

    save_jobs(jobs, output_file)
    print(f"  ✓ All jobs with descriptions saved to {output_file}")

    print("\n" + "=" * 60)
    print("✓ COMPLETE!")
    print("=" * 60)

    return jobs


def scrape_meta(
    force: bool = False,
    fetch_descriptions: bool = True,
    description_limit: Optional[int] = None,
):
    """
    Scrape Meta jobs and store them in meta/meta.json.
    Mirrors the (path, count, was_scraped) contract used by other scrapers.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, "meta.json")

    if not force and os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            jobs = (
                existing.get("jobs", existing)
                if isinstance(existing, dict)
                else existing
            )
            if isinstance(jobs, list):
                if isinstance(existing, dict):
                    last_scraped_str = existing.get("last_scraped")
                    if last_scraped_str:
                        try:
                            last_scraped = datetime.fromisoformat(last_scraped_str)
                            hours_elapsed = (
                                datetime.now() - last_scraped
                            ).total_seconds() / 3600
                            print(
                                f"Existing Meta data scraped {hours_elapsed:.1f} hours ago. Reusing."
                            )
                        except Exception:
                            print(
                                "Existing Meta data found. Reusing without rescraping."
                            )
                    else:
                        print("Existing Meta data found. Reusing without rescraping.")
                else:
                    print("Existing Meta data found. Reusing without rescraping.")
                return json_path, len(jobs), False
        except (OSError, json.JSONDecodeError):
            pass

    jobs = main(
        fetch_descriptions=fetch_descriptions,
        description_limit=description_limit,
    )

    job_count = len(jobs) if isinstance(jobs, list) else 0
    return json_path, job_count, True


if __name__ == "__main__":
    import sys

    # Default: Fetch everything (jobs + descriptions)
    # This will:
    #   1. Fetch job listings and save to meta.json
    #   2. Fetch descriptions in parallel (10 workers)
    #   3. Update meta.json with descriptions
    #   4. Cache descriptions in meta_descriptions_cache.json
    #
    # Workflow Options:
    #
    #   Option A: Everything at once (default)
    #       python3 main.py
    #
    #   Option B: Two-phase approach (safer, can resume)
    #       Phase 1: python3 -c "from main import main; main(fetch_descriptions=False)"
    #       Phase 2: python3 -c "from main import fetch_descriptions_only; fetch_descriptions_only()"
    #
    #   Option C: Test with limited descriptions
    #       python3 -c "from main import main; main(fetch_descriptions=True, description_limit=10)"
    #
    # Cache benefits:
    #   - First run: Fetches descriptions with 10 parallel workers (~4-5 min for 1000 jobs)
    #   - Subsequent runs: Only fetches NEW jobs (seconds to minutes)
    #   - To clear cache: delete meta_descriptions_cache.json
    #
    # Performance:
    #   - Sequential (old): ~40-50 minutes for 1000 descriptions
    #   - Parallel (new): ~4-5 minutes for 1000 descriptions (10x faster!)

    # NOTE: Descriptions are disabled by default because Meta requires login
    # To attempt description fetching anyway, use:
    # python3 -c "from main import main; main(fetch_descriptions=True)"

    if len(sys.argv) > 1 and sys.argv[1] == "--descriptions-only":
        # Only fetch descriptions for existing jobs (will likely fail due to login requirement)
        print("⚠️  WARNING: Meta requires login for job descriptions. This will likely fail.")
        fetch_descriptions_only()
    else:
        # Default: fetch job listings only (no descriptions due to Meta's login requirement)
        scrape_meta(force=True, fetch_descriptions=False, description_limit=None)
