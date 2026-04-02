#!/usr/bin/env python3
"""
Gem ATS Job Scraper

A production-ready Python client for scraping job listings from Gem ATS (Applicant Tracking System).
This scraper uses the public GraphQL API to fetch job postings for any company hosted on jobs.gem.com.

Author: Reverse API
License: MIT
"""

import json
import requests
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Location:
    """Represents a job location."""
    id: str
    name: str
    city: str
    iso_country: str
    is_remote: bool
    ext_id: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Location':
        """Create Location instance from API response."""
        return cls(
            id=data.get('id', ''),
            name=data.get('name', ''),
            city=data.get('city', ''),
            iso_country=data.get('isoCountry', ''),
            is_remote=data.get('isRemote', False),
            ext_id=data.get('extId', '')
        )


@dataclass
class Department:
    """Represents a job department."""
    id: str
    name: str
    ext_id: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Department':
        """Create Department instance from API response."""
        return cls(
            id=data.get('id', ''),
            name=data.get('name', ''),
            ext_id=data.get('extId', '')
        )


@dataclass
class Job:
    """Represents job details."""
    id: str
    department: Optional[Department]
    location_type: str
    employment_type: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Job':
        """Create Job instance from API response."""
        dept_data = data.get('department')
        department = Department.from_dict(dept_data) if dept_data else None

        return cls(
            id=data.get('id', ''),
            department=department,
            location_type=data.get('locationType', ''),
            employment_type=data.get('employmentType', '')
        )


@dataclass
class JobPosting:
    """Represents a complete job posting."""
    id: str
    ext_id: str
    title: str
    locations: List[Location]
    job: Job

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JobPosting':
        """Create JobPosting instance from API response."""
        locations = [Location.from_dict(loc) for loc in data.get('locations', [])]
        job = Job.from_dict(data.get('job', {}))

        return cls(
            id=data.get('id', ''),
            ext_id=data.get('extId', ''),
            title=data.get('title', ''),
            locations=locations,
            job=job
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        return result


@dataclass
class CompanyInfo:
    """Represents company/job board information."""
    id: str
    team_display_name: str
    description_html: Optional[str]
    page_title: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CompanyInfo':
        """Create CompanyInfo instance from API response."""
        return cls(
            id=data.get('id', ''),
            team_display_name=data.get('teamDisplayName', ''),
            description_html=data.get('descriptionHtml'),
            page_title=data.get('pageTitle', '')
        )


class GemATSScraper:
    """
    A scraper for Gem ATS job boards.

    This class provides methods to fetch job listings and company information
    from Gem ATS using their public GraphQL API.
    """

    BASE_URL = "https://jobs.gem.com"
    API_ENDPOINT = f"{BASE_URL}/api/public/graphql/batch"

    # GraphQL queries
    JOB_BOARD_THEME_QUERY = """
    query JobBoardTheme($boardId: String!) {
      publicBrandingTheme(externalId: $boardId) {
        id
        theme
        __typename
      }
    }
    """

    JOB_BOARD_LIST_QUERY = """
    query JobBoardList($boardId: String!) {
      oatsExternalJobPostings(boardId: $boardId) {
        jobPostings {
          id
          extId
          title
          locations {
            id
            name
            city
            isoCountry
            isRemote
            extId
            __typename
          }
          job {
            id
            department {
              id
              name
              extId
              __typename
            }
            locationType
            employmentType
            __typename
          }
          __typename
        }
        __typename
      }
      oatsExternalJobPostingsFilters(boardId: $boardId) {
        type
        displayName
        rawValue
        value
        count
        __typename
      }
      jobBoardExternal(vanityUrlPath: $boardId) {
        id
        teamDisplayName
        descriptionHtml
        pageTitle
        __typename
      }
    }
    """

    def __init__(self, session: Optional[requests.Session] = None):
        """
        Initialize the scraper.

        Args:
            session: Optional requests.Session for connection pooling
        """
        self.session = session or requests.Session()
        self._setup_headers()

    def _setup_headers(self) -> None:
        """Set up default headers for API requests."""
        self.session.headers.update({
            'Accept': '*/*',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
            'Referer': self.BASE_URL,
            'Origin': self.BASE_URL,
            'batch': 'true',
        })

    def get_jobs(self, company_id: str) -> Dict[str, Any]:
        """
        Fetch all job postings for a given company.

        Args:
            company_id: The company identifier (e.g., 'accel', 'alex-and-ani')

        Returns:
            Dictionary containing job postings, filters, and company info

        Raises:
            requests.RequestException: If the API request fails
            ValueError: If the response cannot be parsed
        """
        # Prepare the batch GraphQL request
        payload = [
            {
                "operationName": "JobBoardTheme",
                "variables": {"boardId": company_id},
                "query": self.JOB_BOARD_THEME_QUERY
            },
            {
                "operationName": "JobBoardList",
                "variables": {"boardId": company_id},
                "query": self.JOB_BOARD_LIST_QUERY
            }
        ]

        try:
            response = self.session.post(
                self.API_ENDPOINT,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()

            # Extract the job board list response (second item in batch)
            if len(data) < 2:
                raise ValueError("Unexpected API response format")

            job_board_data = data[1].get('data', {})

            return {
                'job_postings': job_board_data.get('oatsExternalJobPostings', {}).get('jobPostings', []),
                'filters': job_board_data.get('oatsExternalJobPostingsFilters', []),
                'company_info': job_board_data.get('jobBoardExternal', {}),
                'theme': data[0].get('data', {}).get('publicBrandingTheme')
            }

        except requests.RequestException as e:
            raise requests.RequestException(f"Failed to fetch jobs for {company_id}: {str(e)}")
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"Failed to parse API response: {str(e)}")

    def get_job_postings(self, company_id: str) -> List[JobPosting]:
        """
        Fetch and parse job postings for a company.

        Args:
            company_id: The company identifier

        Returns:
            List of JobPosting objects
        """
        data = self.get_jobs(company_id)
        job_postings_data = data.get('job_postings', [])

        return [JobPosting.from_dict(job_data) for job_data in job_postings_data]

    def get_company_info(self, company_id: str) -> CompanyInfo:
        """
        Fetch company information.

        Args:
            company_id: The company identifier

        Returns:
            CompanyInfo object
        """
        data = self.get_jobs(company_id)
        company_data = data.get('company_info', {})

        return CompanyInfo.from_dict(company_data)

    def get_jobs_by_department(self, company_id: str) -> Dict[str, List[JobPosting]]:
        """
        Fetch jobs grouped by department.

        Args:
            company_id: The company identifier

        Returns:
            Dictionary mapping department names to lists of job postings
        """
        job_postings = self.get_job_postings(company_id)

        # Group by department
        by_department: Dict[str, List[JobPosting]] = {}

        for posting in job_postings:
            dept_name = posting.job.department.name if posting.job.department else "Other"

            if dept_name not in by_department:
                by_department[dept_name] = []

            by_department[dept_name].append(posting)

        return by_department

    def get_jobs_by_location(self, company_id: str) -> Dict[str, List[JobPosting]]:
        """
        Fetch jobs grouped by location.

        Args:
            company_id: The company identifier

        Returns:
            Dictionary mapping location names to lists of job postings
        """
        job_postings = self.get_job_postings(company_id)

        # Group by location
        by_location: Dict[str, List[JobPosting]] = {}

        for posting in job_postings:
            for location in posting.locations:
                loc_name = location.name

                if loc_name not in by_location:
                    by_location[loc_name] = []

                by_location[loc_name].append(posting)

        return by_location

    def export_to_json(self, company_id: str, filename: Optional[str] = None) -> str:
        """
        Export job postings to a JSON file.

        Args:
            company_id: The company identifier
            filename: Optional output filename (default: {company_id}_jobs.json)

        Returns:
            Path to the exported file
        """
        if filename is None:
            filename = f"{company_id}_jobs.json"

        data = self.get_jobs(company_id)

        # Convert to serializable format
        export_data = {
            'company_id': company_id,
            'scraped_at': datetime.now().isoformat(),
            'company_info': data.get('company_info', {}),
            'job_count': len(data.get('job_postings', [])),
            'job_postings': data.get('job_postings', []),
            'filters': data.get('filters', [])
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        return filename

    def close(self) -> None:
        """Close the session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def main():
    """Example usage of the Gem ATS scraper."""

    print("=" * 80)
    print("Gem ATS Job Scraper - Example Usage")
    print("=" * 80)
    print()

    # Initialize the scraper
    with GemATSScraper() as scraper:

        # Example 1: Fetch jobs from Accel
        print("1. Fetching jobs from Accel...")
        print("-" * 80)

        try:
            company_info = scraper.get_company_info('accel')
            print(f"Company: {company_info.team_display_name}")
            print(f"Page Title: {company_info.page_title}")
            print()

            job_postings = scraper.get_job_postings('accel')
            print(f"Total jobs found: {len(job_postings)}")
            print()

            for i, job in enumerate(job_postings, 1):
                print(f"{i}. {job.title}")
                print(f"   Type: {job.job.employment_type}")
                print(f"   Location Type: {job.job.location_type}")
                if job.locations:
                    locations = ", ".join([loc.name for loc in job.locations])
                    print(f"   Locations: {locations}")
                if job.job.department:
                    print(f"   Department: {job.job.department.name}")
                print(f"   Job ID: {job.ext_id}")
                print()

        except Exception as e:
            print(f"Error fetching Accel jobs: {e}")

        print()

        # Example 2: Fetch jobs from Alex and Ani, grouped by department
        print("2. Fetching jobs from Alex and Ani (grouped by department)...")
        print("-" * 80)

        try:
            jobs_by_dept = scraper.get_jobs_by_department('alex-and-ani')

            for dept_name, jobs in jobs_by_dept.items():
                print(f"\n{dept_name} ({len(jobs)} jobs):")
                for job in jobs:
                    locations = ", ".join([loc.name for loc in job.locations])
                    print(f"  - {job.title} | {locations}")

        except Exception as e:
            print(f"Error fetching Alex and Ani jobs: {e}")

        print()
        print("-" * 80)

        # Example 3: Export jobs to JSON
        print("\n3. Exporting jobs to JSON files...")
        print("-" * 80)

        try:
            accel_file = scraper.export_to_json('accel')
            print(f"Accel jobs exported to: {accel_file}")

            alex_file = scraper.export_to_json('alex-and-ani')
            print(f"Alex and Ani jobs exported to: {alex_file}")

        except Exception as e:
            print(f"Error exporting jobs: {e}")

    print()
    print("=" * 80)
    print("Done!")
    print("=" * 80)


if __name__ == "__main__":
    main()
