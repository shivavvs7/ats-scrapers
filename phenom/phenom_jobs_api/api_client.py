#!/usr/bin/env python3
"""
Phenom Jobs API Client

This client allows you to search for jobs on Phenom-powered career sites.
Supports companies like Bell Canada, GE Healthcare, and many others.
"""

import requests
from typing import Dict, List, Optional, Any
import json
from urllib.parse import urlparse


class PhenomJobsClient:
    """
    Client for interacting with Phenom Jobs API.

    This API is used by many corporate career sites including:
    - Bell Canada (jobs.bell.ca)
    - GE Healthcare (careers.gehealthcare.com)
    - And many other companies
    """

    def __init__(self, base_url: str, company_code: str, locale: str = "en", country: str = "us"):
        """
        Initialize the Phenom Jobs client.

        Args:
            base_url: The base URL of the career site (e.g., "https://jobs.bell.ca")
            company_code: The company identifier (e.g., "BECACA" for Bell Canada, "GEVGHLGLOBAL" for GE)
            locale: Language/locale code (e.g., "en_ca", "en_global")
            country: Country code (e.g., "ca", "global")
        """
        self.base_url = base_url.rstrip('/')
        self.company_code = company_code
        self.locale = locale
        self.country = country
        self.session = requests.Session()
        self.csrf_token = None

        # Initialize session by making a request to the main page
        self._initialize_session()

    def _initialize_session(self):
        """Initialize the session and get CSRF token."""
        try:
            # Visit the main search page to get cookies and CSRF token
            search_url = f"{self.base_url}/{self.country}/{self.locale.split('_')[0]}/search-results"
            response = self.session.get(search_url, timeout=30)
            response.raise_for_status()

            # Extract CSRF token from cookies or page
            for cookie in self.session.cookies:
                if 'csrf' in cookie.name.lower():
                    self.csrf_token = cookie.value
                    break

            # If no CSRF in cookies, try to find it in the page
            if not self.csrf_token and 'csrfToken' in response.text:
                import re
                match = re.search(r'"csrfToken"\s*:\s*"([^"]+)"', response.text)
                if match:
                    self.csrf_token = match.group(1)

            print(f"Session initialized. CSRF token: {'Found' if self.csrf_token else 'Not found'}")

        except Exception as e:
            print(f"Warning: Could not initialize session: {e}")

    def search_jobs(
        self,
        keywords: str = "",
        location: str = "",
        category: str = "",
        from_index: int = 0,
        size: int = 10,
        sort_by: str = "",
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Search for jobs.

        Args:
            keywords: Search keywords (job title, skills, etc.)
            location: Location filter (city, state, country)
            category: Job category filter
            from_index: Starting index for pagination (0 for first page, 10 for second, etc.)
            size: Number of results per page (default: 10)
            sort_by: Sort order (empty for relevance, "date" for most recent)
            filters: Additional filters as a dict (e.g., {"state": ["California"], "city": ["Toronto"]})

        Returns:
            Dictionary containing job results and metadata
        """
        url = f"{self.base_url}/widgets"

        # Build the request payload
        payload = {
            "lang": self.locale,
            "deviceType": "desktop",
            "country": self.country,
            "pageName": "search-results",
            "ddoKey": "refineSearch",
            "sortBy": sort_by,
            "subsearch": "",
            "from": from_index,
            "jobs": True,
            "counts": True,
            "all_fields": [
                "category",
                "jobFamilies",
                "country",
                "state",
                "city",
                "experienceLevel"
            ],
            "size": size,
            "clearAll": False,
            "jdsource": "facets",
            "isSliderEnable": False,
            "pageId": "page20",
            "siteType": "external",
            "keywords": keywords,
            "global": True,
            "selected_fields": filters or {},
            "locationData": {}
        }

        # Add location if provided
        if location:
            payload["location"] = location

        # Add category if provided
        if category:
            if "selected_fields" not in payload:
                payload["selected_fields"] = {}
            payload["selected_fields"]["category"] = [category]

        # Set headers
        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/{self.country}/{self.locale.split('_')[0]}/search-results"
        }

        if self.csrf_token:
            headers["x-csrf-token"] = self.csrf_token

        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "error": str(e),
                "status_code": getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
            }

    def get_all_jobs(
        self,
        keywords: str = "",
        location: str = "",
        category: str = "",
        max_results: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all jobs matching the criteria (handles pagination automatically).

        Args:
            keywords: Search keywords
            location: Location filter
            category: Job category filter
            max_results: Maximum number of results to return (None for all)
            filters: Additional filters

        Returns:
            List of all job dictionaries
        """
        all_jobs = []
        from_index = 0
        page_size = 100  # Larger page size for efficiency

        while True:
            result = self.search_jobs(
                keywords=keywords,
                location=location,
                category=category,
                from_index=from_index,
                size=page_size,
                filters=filters
            )

            # Check for errors
            if "error" in result:
                print(f"Error fetching jobs: {result['error']}")
                break

            # Extract jobs from response
            jobs = self._extract_jobs(result)

            if not jobs:
                break

            all_jobs.extend(jobs)

            # Check if we've reached max results
            if max_results and len(all_jobs) >= max_results:
                all_jobs = all_jobs[:max_results]
                break

            # Check if there are more results
            total_hits = self._get_total_hits(result)
            if total_hits is None or from_index + page_size >= total_hits:
                break

            from_index += page_size
            print(f"Fetched {len(all_jobs)} of {total_hits} jobs...")

        return all_jobs

    def _extract_jobs(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract jobs list from API response."""
        try:
            # The response structure may vary, check common paths
            if "refineSearch" in response:
                rs = response["refineSearch"]
                # Check for data.jobs first (most common structure)
                if "data" in rs and "jobs" in rs["data"]:
                    return rs["data"]["jobs"]
                # Check for direct hits array
                elif "hits" in rs and isinstance(rs["hits"], list):
                    return rs["hits"]
            elif "jobs" in response:
                return response["jobs"]
            elif "hits" in response and isinstance(response["hits"], list):
                return response["hits"]
            else:
                # Response might be the jobs list itself
                if isinstance(response, list):
                    return response
                # Check for nested data
                if "data" in response:
                    data = response["data"]
                    if "jobs" in data and isinstance(data["jobs"], list):
                        return data["jobs"]
                    elif isinstance(data, list):
                        return data
                for key in ["results", "items"]:
                    if key in response and isinstance(response[key], list):
                        return response[key]
        except Exception as e:
            print(f"Error extracting jobs: {e}")

        return []

    def _get_total_hits(self, response: Dict[str, Any]) -> Optional[int]:
        """Get total number of available jobs from response."""
        try:
            if "refineSearch" in response:
                rs = response["refineSearch"]
                if "totalHits" in rs:
                    return rs["totalHits"]
                elif "total" in rs:
                    return rs["total"]
            elif "totalHits" in response:
                return response["totalHits"]
            elif "total" in response:
                return response["total"]
        except:
            pass
        return None

    def get_job_details(self, job_id: str) -> Dict[str, Any]:
        """
        Get detailed information for a specific job.

        Args:
            job_id: The job ID

        Returns:
            Dictionary with job details
        """
        url = f"{self.base_url}/widgets"

        payload = {
            "lang": self.locale,
            "deviceType": "desktop",
            "country": self.country,
            "pageName": "job-details",
            "ddoKey": "jobDetails",
            "job_id": job_id,
            "siteType": "external"
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*"
        }

        if self.csrf_token:
            headers["x-csrf-token"] = self.csrf_token

        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "error": str(e),
                "status_code": getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
            }


def main():
    """Example usage of the Phenom Jobs API client."""

    print("=" * 60)
    print("Phenom Jobs API Client - Examples")
    print("=" * 60)

    # Example 1: Bell Canada
    print("\n### Example 1: Searching Bell Canada jobs ###\n")
    bell_client = PhenomJobsClient(
        base_url="https://jobs.bell.ca",
        company_code="BECACA",
        locale="en_ca",
        country="ca"
    )

    print("Fetching ALL jobs from Bell Canada (this may take a while)...")
    all_jobs = bell_client.get_all_jobs()  # Limit to 20 for demo
    print(f"\nTotal jobs fetched: {len(all_jobs)}")

    # Show some statistics
    if all_jobs:
        categories = {}
        for job in all_jobs:
            cat = job.get("category", job.get("jobCategory", "Unknown"))
            categories[cat] = categories.get(cat, 0) + 1

        print("\nJobs by category:")
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  - {cat}: {count} jobs")

    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
