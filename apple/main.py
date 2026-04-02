#!/usr/bin/env python3
"""
Apple Jobs Scraper

Scrapes job postings from Apple's careers website and saves them to apple.json.
Follows the same pattern as other scrapers (google, microsoft, etc.) for easy integration.

Two-phase approach:
1. First fetch all jobs quickly (without details) and save them
2. Then fetch job descriptions incrementally using a cache to avoid redundant work
"""

import json
import os
import sys
import importlib.util
from datetime import datetime
from pathlib import Path

# Import api_client from the apple directory using importlib to avoid conflicts
script_dir = Path(__file__).resolve().parent
api_client_path = script_dir / "api_client.py"
spec = importlib.util.spec_from_file_location("apple_api_client", api_client_path)
apple_api_client = importlib.util.module_from_spec(spec)
sys.modules["apple_api_client"] = apple_api_client
spec.loader.exec_module(apple_api_client)
AppleJobsAPI = apple_api_client.AppleJobsAPI

# Import cache manager
cache_manager_path = script_dir / "cache_manager.py"
spec = importlib.util.spec_from_file_location("cache_manager", cache_manager_path)
cache_manager = importlib.util.module_from_spec(spec)
sys.modules["cache_manager"] = cache_manager
spec.loader.exec_module(cache_manager)
JobDescriptionCache = cache_manager.JobDescriptionCache


def scrape_apple_jobs(force: bool = False) -> tuple[str, int, bool]:
    """
    Scrape Apple jobs and store them in apple/apple.json.
    Returns (json_path, num_jobs, was_scraped).

    Args:
        force: If True, force scraping even if data was recently scraped

    Returns:
        Tuple of (json_path_str, num_jobs, was_scraped)
    """
    json_path = str(script_dir / "apple.json")

    # Check if file exists and is fresh (unless force=True)
    # Default freshness: 6 hours (since Apple scraping can be slow)
    max_age_hours = 6.0
    if not force and os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, dict):
                jobs = existing.get("jobs", [])
                last_scraped_str = existing.get("last_scraped")

                # Check freshness based on last_scraped timestamp
                if last_scraped_str and jobs:
                    try:
                        last_scraped = datetime.fromisoformat(last_scraped_str)
                        # Handle timezone-aware datetimes
                        if last_scraped.tzinfo is not None:
                            from datetime import timezone

                            now = datetime.now(timezone.utc)
                        else:
                            now = datetime.now()
                            last_scraped = last_scraped.replace(tzinfo=None)
                        hours_elapsed = (now - last_scraped).total_seconds() / 3600
                        if hours_elapsed < max_age_hours:
                            print(
                                f"Existing Apple data found (scraped {hours_elapsed:.1f} hours ago). Reusing without rescraping."
                            )
                            return json_path, len(jobs), False
                        else:
                            print(
                                f"Existing Apple data is stale ({hours_elapsed:.1f} hours old, max {max_age_hours}h). Rescraping..."
                            )
                    except (ValueError, TypeError):
                        # If timestamp parsing fails, check file modification time as fallback
                        file_mtime = Path(json_path).stat().st_mtime
                        hours_elapsed = (datetime.now().timestamp() - file_mtime) / 3600
                        if hours_elapsed < max_age_hours and jobs:
                            print(
                                f"Existing Apple data found (file modified {hours_elapsed:.1f} hours ago). Reusing without rescraping."
                            )
                            return json_path, len(jobs), False
                elif jobs:
                    # No timestamp but has jobs - check file modification time
                    file_mtime = Path(json_path).stat().st_mtime
                    hours_elapsed = (datetime.now().timestamp() - file_mtime) / 3600
                    if hours_elapsed < max_age_hours:
                        print(
                            f"Existing Apple data found (file modified {hours_elapsed:.1f} hours ago). Reusing without rescraping."
                        )
                        return json_path, len(jobs), False
            else:
                # Old format (list instead of dict)
                if existing:
                    print(
                        "Existing Apple data found (old format). Reusing without rescraping."
                    )
                    return json_path, len(existing), False
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading existing Apple data: {e}. Will rescrape.")

    # Initialize client and cache
    print("Initializing...")
    client = AppleJobsAPI(locale="en-us")
    cache = JobDescriptionCache()

    # === PHASE 1: Fetch all jobs quickly (without details) ===
    print("\n" + "=" * 80)
    print("PHASE 1: Fetching all Apple jobs (basic info only)...")
    print("=" * 80)
    all_jobs = client.search_all_jobs()

    if not all_jobs:
        print("No jobs found!")
        return json_path, 0, True

    print(f"Found {len(all_jobs)} total jobs")

    # Save basic job list immediately
    jobs_data = []
    for job in all_jobs:
        locations = [loc.name for loc in job.locations] if job.locations else ["N/A"]
        job_dict = {
            "url": job.url,
            "title": job.postingTitle,
            "locations": locations,
            "location": locations[0] if locations else "N/A",
            "description": job.jobSummary,  # Temporary - will be replaced with full description
            "postingDate": job.postingDate,
            "positionId": job.positionId,
            "id": job.id,
            "reqId": job.reqId,
        }
        jobs_data.append(job_dict)

    # Save basic job list
    wrapped = {
        "last_scraped": datetime.now().isoformat(),
        "name": "Apple",
        "jobs": jobs_data,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(wrapped, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved {len(jobs_data)} jobs (basic info) to {json_path}")

    # === PHASE 2: Fetch job descriptions with caching ===
    print("\n" + "=" * 80)
    print("PHASE 2: Fetching detailed job descriptions...")
    print("=" * 80)

    # Get current position IDs
    current_position_ids = {job.positionId for job in all_jobs}

    # Clean up cache for deleted jobs
    deleted_count = cache.cleanup_deleted_jobs(current_position_ids)
    if deleted_count > 0:
        print(f"✓ Removed {deleted_count} deleted job(s) from cache")

    # Identify jobs that need details fetching
    jobs_needing_details = []
    cached_count = 0

    for job in all_jobs:
        if cache.has(job.positionId):
            # Load from cache
            cached_details = cache.get(job.positionId)
            job.description = cached_details['description']
            job.minimumQualifications = cached_details['minimumQualifications']
            job.preferredQualifications = cached_details['preferredQualifications']
            job.payAndBenefits = cached_details['payAndBenefits']
            cached_count += 1
        else:
            jobs_needing_details.append(job)

    print(f"✓ Loaded {cached_count} job(s) from cache")
    print(f"→ Need to fetch details for {len(jobs_needing_details)} job(s)")

    # Fetch details for uncached jobs
    if jobs_needing_details:
        print(f"\nFetching details for {len(jobs_needing_details)} jobs with 50 concurrent requests...")
        detailed_jobs = client.get_all_job_details(
            jobs_needing_details,
            max_concurrent=50,
            show_progress=True
        )

        # Update cache with newly fetched details
        for job in detailed_jobs:
            cache.set(
                job.positionId,
                job.description or '',
                job.minimumQualifications or '',
                job.preferredQualifications or '',
                job.payAndBenefits
            )

        # Save updated cache
        cache.save_cache()
        print(f"✓ Updated cache with {len(detailed_jobs)} new job detail(s)")
    else:
        print("✓ All jobs already cached, no new fetches needed!")

    # === PHASE 3: Merge details and save final output ===
    print("\n" + "=" * 80)
    print("PHASE 3: Merging details and saving final output...")
    print("=" * 80)

    # Create final job data with full descriptions
    final_jobs_data = []
    for job in all_jobs:
        locations = [loc.name for loc in job.locations] if job.locations else ["N/A"]
        job_dict = {
            "url": job.url,
            "title": job.postingTitle,
            "locations": locations,
            "location": locations[0] if locations else "N/A",
            "description": job.full_description,  # Full description with all details
            "postingDate": job.postingDate,
            "positionId": job.positionId,
            "id": job.id,
            "reqId": job.reqId,
        }
        final_jobs_data.append(job_dict)

    # Save final output
    wrapped = {
        "last_scraped": datetime.now().isoformat(),
        "name": "Apple",
        "jobs": final_jobs_data,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(wrapped, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved {len(final_jobs_data)} jobs with full descriptions to {json_path}")
    print("\n" + "=" * 80)
    print("SCRAPING COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    print(f"Cache stats: {len(cache)} total entries")

    return json_path, len(final_jobs_data), True


if __name__ == "__main__":
    scrape_apple_jobs(force=True)
