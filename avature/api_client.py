"""
Avature Careers API Client

This module provides a client for scraping job listings from any Avature-powered
career portal. Works with Bloomberg, IBM, and other companies using Avature.

Example URLs:
- https://bloomberg.avature.net/careers/SearchJobs/
- https://careers.ibm.com/en_US/careers/SearchJobs/
"""

import requests
from typing import Dict, List, Optional, Any, Iterator
from dataclasses import dataclass
import time
from bs4 import BeautifulSoup
import logging
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class AvatureJob:
    """Represents a job listing from Avature"""
    job_id: str
    title: str
    location: str
    url: str
    department: Optional[str] = None
    description: Optional[str] = None
    posted_date: Optional[str] = None


class AvatureCareersAPI:
    """
    Client for interacting with Avature-powered career sites.
    
    Usage:
        client = AvatureCareersAPI("https://bloomberg.avature.net")
        jobs = client.get_all_jobs()
        for job in jobs:
            print(f"{job.title} - {job.location}")
    """

    def __init__(self, base_url: str, rate_limit: float = 0.5):
        """
        Initialize the Avature Careers API client.
        
        Args:
            base_url: Base URL of the Avature career site (e.g., "https://bloomberg.avature.net")
            rate_limit: Minimum seconds between requests (default: 0.5)
        """
        self.base_url = base_url.rstrip('/')
        self.rate_limit = rate_limit
        self.last_request_time = 0
        
        # Parse URL components
        parsed = urlparse(self.base_url)
        self.domain = parsed.netloc
        self.scheme = parsed.scheme

        self.session = requests.Session()

        # Set up session headers to mimic browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                         'AppleWebKit/537.36 (KHTML, like Gecko) '
                         'Chrome/143.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
                     'image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
        })

        logger.info(f"Avature Careers API client initialized for {self.domain}")

    def _rate_limit_wait(self) -> None:
        """Enforce rate limiting between requests"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> requests.Response:
        """Make an HTTP request with rate limiting and error handling."""
        self._rate_limit_wait()

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"Request failed: {method} {url} - {str(e)}")
            raise

    def get_jobs_page(
        self,
        offset: int = 0,
        records_per_page: int = 12
    ) -> List[Dict[str, Any]]:
        """
        Retrieve a single page of job listings.
        
        Args:
            offset: Number of jobs to skip (for pagination)
            records_per_page: Number of jobs to return per page
            
        Returns:
            List of job dictionaries with basic information
        """
        url = f"{self.base_url}/careers/SearchJobs/"
        params = {
            'jobOffset': offset,
            'jobRecordsPerPage': records_per_page
        }

        logger.info(f"Fetching jobs page: offset={offset}, limit={records_per_page}")

        try:
            response = self._make_request('GET', url, params=params)
            return self._parse_job_listings(response.text)
        except Exception as e:
            logger.error(f"Failed to fetch jobs page: {str(e)}")
            return []

    def _parse_job_listings(self, html_content: str) -> List[Dict[str, Any]]:
        """
        Parse job listings from HTML response.
        
        Args:
            html_content: Raw HTML content from search page
            
        Returns:
            List of parsed job dictionaries
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        jobs = []

        # Avature job listings are typically in article elements with job data
        # Try multiple selectors to handle different Avature configurations
        job_elements = (
            soup.find_all('article', class_='job') or
            soup.find_all('div', class_='job-item') or
            soup.find_all('li', class_='job-listing') or
            soup.find_all('tr', class_='job') or
            soup.find_all('div', attrs={'data-job-id': True})
        )

        if not job_elements:
            # Fallback: look for links to job detail pages
            job_elements = soup.find_all('a', href=lambda x: x and '/JobDetail/' in x)

        for element in job_elements:
            try:
                job = self._parse_job_element(element)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.warning(f"Failed to parse job element: {str(e)}")
                continue

        logger.info(f"Parsed {len(jobs)} jobs from page")
        return jobs

    def _parse_job_element(self, element) -> Optional[Dict[str, Any]]:
        """Parse a single job element from HTML."""
        # Extract job link
        link = element if element.name == 'a' else element.find('a')
        if not link:
            return None
        
        href = link.get('href', '')
        if not href:
            return None
        
        # Skip "Apply" links - they usually contain "Apply" text or are just action links
        link_text = link.get_text(strip=True)
        if link_text.lower() in ['apply', 'apply now', 'apply online', '']:
            return None

        # Build full URL
        if href.startswith('http'):
            job_url = href
        else:
            job_url = f"{self.base_url}{href}"

        # Extract job ID from URL
        # Format: /careers/JobDetail/{title}/{job_id} or /careers/JobDetail/{job_id}
        url_parts = href.split('/')
        job_id = url_parts[-1] if url_parts else 'unknown'
        # Remove any query parameters
        job_id = job_id.split('?')[0]

        # Extract title
        title_elem = (
            element.find('h2') or
            element.find('h3') or
            element.find(class_=['job-title', 'position-title', 'title']) or
            link
        )
        title = title_elem.get_text(strip=True) if title_elem else 'No title'
        
        # Skip if title is just "Apply" or similar
        if title.lower() in ['apply', 'apply now', 'learn more', 'view job']:
            return None

        # Extract location
        location_elem = (
            element.find(class_=['location', 'job-location']) or
            element.find('span', class_=lambda x: x and 'location' in str(x).lower())
        )
        location = location_elem.get_text(strip=True) if location_elem else ''

        # Extract department
        dept_elem = element.find(class_=['department', 'job-department', 'category'])
        department = dept_elem.get_text(strip=True) if dept_elem else None

        return {
            'job_id': job_id,
            'title': title,
            'location': location,
            'department': department,
            'url': job_url
        }

    def get_all_jobs(
        self,
        limit: Optional[int] = None,
        records_per_page: int = 12
    ) -> Iterator[AvatureJob]:
        """
        Retrieve all available job listings with pagination.
        
        Args:
            limit: Maximum number of jobs to retrieve (None for all)
            records_per_page: Number of jobs per page request
            
        Yields:
            AvatureJob objects
        """
        offset = 0
        total_yielded = 0

        logger.info(f"Starting to fetch all jobs (limit={limit})")

        while True:
            # Check if we've reached the limit
            if limit and total_yielded >= limit:
                break

            # Fetch next page
            jobs_page = self.get_jobs_page(offset=offset, records_per_page=records_per_page)

            # Break if no more jobs
            if not jobs_page:
                logger.info("No more jobs found")
                break

            for job_data in jobs_page:
                if limit and total_yielded >= limit:
                    break

                yield AvatureJob(**job_data)
                total_yielded += 1

            # If we got fewer jobs than requested, we've reached the end
            if len(jobs_page) < records_per_page:
                break

            offset += records_per_page
            logger.info(f"Total jobs collected: {total_yielded}")

        logger.info(f"Finished fetching jobs. Total: {total_yielded}")

    def get_job_detail(self, job_id: str, job_title_slug: str = "") -> Optional[Dict[str, Any]]:
        """
        Retrieve detailed information for a specific job.
        
        Args:
            job_id: The unique job identifier
            job_title_slug: URL-friendly job title (optional)
            
        Returns:
            Dictionary with detailed job information, or None on error
        """
        if not job_title_slug:
            job_title_slug = "job"

        url = f"{self.base_url}/careers/JobDetail/{job_title_slug}/{job_id}"

        logger.info(f"Fetching job detail for ID: {job_id}")

        try:
            response = self._make_request('GET', url)
            return self._parse_job_detail(response.text, job_id)
        except Exception as e:
            logger.error(f"Failed to fetch job detail for {job_id}: {str(e)}")
            return None

    def _parse_job_detail(self, html_content: str, job_id: str) -> Dict[str, Any]:
        """Parse detailed job information from HTML."""
        soup = BeautifulSoup(html_content, 'html.parser')

        job_detail = {'job_id': job_id}

        # Extract title
        title_elem = (
            soup.find('h1') or
            soup.find(class_=['job-title', 'position-title'])
        )
        job_detail['title'] = title_elem.get_text(strip=True) if title_elem else 'No title'

        # Extract location
        location_elem = soup.find(class_=['location', 'job-location'])
        job_detail['location'] = location_elem.get_text(strip=True) if location_elem else ''

        # Extract description
        desc_elem = (
            soup.find(class_=['description', 'job-description']) or
            soup.find('div', {'id': 'job-description'})
        )
        job_detail['description'] = desc_elem.get_text(strip=True) if desc_elem else ''

        # Extract department
        dept_elem = soup.find(class_=['department', 'job-department'])
        job_detail['department'] = dept_elem.get_text(strip=True) if dept_elem else None

        return job_detail

    def close(self) -> None:
        """Close the session and cleanup resources"""
        self.session.close()
        logger.info("Avature Careers API client closed")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


def extract_company_name(url: str) -> str:
    """Extract company name from Avature URL."""
    parsed = urlparse(url)
    domain = parsed.netloc
    
    # Extract subdomain as company name
    # e.g., bloomberg.avature.net -> Bloomberg
    # e.g., careers.ibm.com -> IBM
    parts = domain.split('.')
    if len(parts) >= 2:
        company = parts[0]
        # Special cases
        if company == 'careers' and len(parts) > 2:
            company = parts[1]
        # Capitalize
        return company.replace('-', ' ').title()
    
    return domain


def extract_base_url(url: str) -> str:
    """Extract base URL for Avature API from any Avature URL."""
    parsed = urlparse(url)
    
    # Reconstruct base URL
    base = f"{parsed.scheme}://{parsed.netloc}"
    
    # Check if there's a path prefix (e.g., /en_US/careers)
    path_parts = parsed.path.split('/')
    if len(path_parts) > 1 and path_parts[1] in ['en_US', 'en_GB', 'fr_CA', 'zh_CN', 'ja_JP', 'pt_BR']:
        base += f"/{path_parts[1]}"
    
    return base


if __name__ == "__main__":
    # Example usage with Bloomberg
    base_url = "https://bloomberg.avature.net"
    
    with AvatureCareersAPI(base_url, rate_limit=0.5) as client:
        print(f"\n=== Fetching jobs from {base_url} ===")
        
        jobs = list(client.get_all_jobs(limit=20))
        print(f"\nFound {len(jobs)} jobs:")
        
        for job in jobs[:5]:
            print(f"- {job.title} ({job.location})")
            print(f"  URL: {job.url}")
