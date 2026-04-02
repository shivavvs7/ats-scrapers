import re
import time
from typing import Any, Dict, List, Optional

import requests


class JoinATSClient:
    """
    A client for scraping job listings from companies using join.com as their ATS.
    """

    BASE_URL = "https://join.com"
    API_URL = f"{BASE_URL}/api/public"

    def __init__(self, user_agent: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "user-agent": user_agent
                or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
                "accept": "application/json",
            }
        )

    def get_company_id(self, company_slug: str) -> Optional[int]:
        """
        Resolves a company slug to its numeric ID by scraping the company page.
        """
        url = f"{self.BASE_URL}/companies/{company_slug}"
        try:
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
            }
            response = self.session.get(url, headers=headers)
            response.raise_for_status()

            match = re.search(r'"company":\{"id":(\d+)', response.text)
            if match:
                return int(match.group(1))

            match = re.search(r'"companyId":(\d+)', response.text)
            if match:
                return int(match.group(1))

            return None
        except requests.RequestException as e:
            print(f"Error looking up company slug '{company_slug}': {e}")
            return None

    def list_jobs(
        self, company_id: int, page: int = 1, page_size: int = 25, locale: str = "en-us"
    ) -> Dict[str, Any]:
        """
        Lists jobs for a given company ID.
        """
        url = f"{self.API_URL}/companies/{company_id}/jobs"
        params = {
            "locale": locale,
            "page": page,
            "pageSize": page_size,
            "withAggregations": "true",
            "sort": "+title",
        }

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error listing jobs for company ID {company_id}: {e}")
            return {"items": [], "pagination": {}}

    def get_all_jobs(
        self, company_slug: str, locale: str = "en-us"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        High-level method to fetch all jobs for a company by its slug.
        Handles company lookup and pagination.
        Returns None if company not found, empty list if no jobs.
        """
        company_id = self.get_company_id(company_slug)
        if not company_id:
            return None

        all_jobs = []
        current_page = 1
        page_size = 50

        while True:
            data = self.list_jobs(
                company_id, page=current_page, page_size=page_size, locale=locale
            )
            items = data.get("items", [])
            if not items:
                break

            all_jobs.extend(items)

            pagination = data.get("pagination", {})
            total_pages = pagination.get("totalPages", 1)

            if current_page >= total_pages:
                break

            current_page += 1
            time.sleep(0.5)

        return all_jobs

    def get_job_details(self, job_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetches detailed information for a specific job, including description.
        """
        url = f"{self.API_URL}/jobs/{job_id}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching details for job ID {job_id}: {e}")
            return None
