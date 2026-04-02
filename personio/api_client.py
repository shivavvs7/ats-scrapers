#!/usr/bin/env python3
"""
Personio Jobs API Client (Python)

A production-ready Python client for fetching job listings from companies using Personio.de as their ATS.
Supports both Personio's main site (JSON API) and company-specific instances (XML feeds).

Author: Converted from TypeScript
Date: 2026-01-21
"""

import re
from typing import List, Optional, Literal
from urllib.parse import urlparse

import requests
from xmltodict import parse as parse_xml

from models.personio import PersonioJob, PersonioOffice, PersonioDepartment, JobDescription


class PersonioAPIError(Exception):
    """Custom exception for Personio API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.status_code = status_code
        self.original_error = original_error
        self.name = "PersonioAPIError"


class PersonioParseError(Exception):
    """Custom exception for Personio parsing errors."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error
        self.name = "PersonioParseError"


class PersonioAPI:
    """Client for interacting with Personio's job listing APIs."""

    def __init__(self, base_url: Optional[str] = None, timeout: int = 30):
        """
        Initialize the Personio API client.

        Args:
            base_url: Base URL for the company's Personio instance.
                     Examples:
                     - "https://www.personio.com" (for Personio's own jobs)
                     - "https://companyname.jobs.personio.com" (for company-specific)
                     If None, defaults to Personio's own API.
            timeout: Request timeout in seconds (default: 30)
        """
        self.base_url = (base_url or "https://www.personio.com").rstrip("/")
        self.timeout = timeout
        self.api_type: Optional[Literal["json", "xml", "search_json"]] = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json, application/xml, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })

        print(f"[PersonioAPI] Initialized with base URL: {self.base_url}")

    def _detect_api_type(self) -> Literal["json", "xml", "search_json"]:
        """Detect which API type this Personio instance uses."""
        if self.api_type:
            return self.api_type

        print("[PersonioAPI] Detecting API type...")

        # Company-specific instances (e.g., company.jobs.personio.com) - try multiple endpoints
        if ".jobs.personio." in self.base_url:
            # Try search.json first (faster and more reliable for company subdomains)
            try:
                url = f"{self.base_url}/search.json"
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type:
                        try:
                            data = response.json()
                            # search.json returns an array directly, not a dict with positions
                            if isinstance(data, list):
                                print("[PersonioAPI] Detected company subdomain - using search.json API")
                                self.api_type = "search_json"
                                return "search_json"
                        except (ValueError, TypeError):
                            pass
            except Exception:
                pass

            # Fall back to XML for company subdomains
            print("[PersonioAPI] Detected company subdomain - using XML API")
            self.api_type = "xml"
            return "xml"

        # Personio main site uses JSON API
        if "www.personio.com" in self.base_url or "personio.com" in self.base_url:
            print("[PersonioAPI] Detected main Personio site - using JSON API")
            self.api_type = "json"
            return "json"

        # Try search.json endpoint first
        try:
            url = f"{self.base_url}/search.json"
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "json" in content_type:
                    try:
                        data = response.json()
                        # search.json returns an array directly
                        if isinstance(data, list):
                            print("[PersonioAPI] Detected search.json API")
                            self.api_type = "search_json"
                            return "search_json"
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

        # Try standard JSON API
        try:
            url = f"{self.base_url}/api/careers/jobs/list/"
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "json" in content_type:
                    print("[PersonioAPI] Detected JSON API via content-type")
                    self.api_type = "json"
                    return "json"
        except Exception:
            print("[PersonioAPI] JSON API detection failed, trying XML...")

        # Default to XML for company instances
        print("[PersonioAPI] Defaulting to XML API")
        self.api_type = "xml"
        return "xml"

    def _fetch_with_timeout(self, url: str, **kwargs) -> requests.Response:
        """Fetch with timeout."""
        try:
            response = self.session.get(url, timeout=self.timeout, **kwargs)
            return response
        except requests.exceptions.Timeout:
            raise PersonioAPIError(f"Request timeout after {self.timeout}s", 408)
        except requests.exceptions.RequestException as e:
            raise PersonioAPIError(
                f"Request failed: {str(e)}",
                original_error=e
            )

    def _clean_cdata(self, value: str) -> str:
        """Clean CDATA content from XML values."""
        if not value:
            return ""
        # Remove CDATA tags and trim whitespace
        return re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", value, flags=re.DOTALL).strip()

    def _create_slug(self, name: str) -> str:
        """Create URL-friendly slug from job name."""
        slug = name.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = re.sub(r"^-+|-+$", "", slug)
        return slug

    def _parse_xml_jobs(self, xml_string: str) -> List[PersonioJob]:
        """Parse XML job feed."""
        try:
            # Check if XML string is empty or whitespace only
            if not xml_string or not xml_string.strip():
                print("[PersonioAPI] Empty XML response received")
                return []

            # Check if response looks like HTML error page or non-XML content
            xml_string = xml_string.strip()
            if xml_string.startswith("<html") or xml_string.startswith("<!DOCTYPE html"):
                raise PersonioParseError("Received HTML instead of XML (likely error page)")

            result = parse_xml(xml_string, process_namespaces=False, dict_constructor=dict)

            # Check if parsing returned None or empty result
            if result is None:
                print("[PersonioAPI] XML parsing returned None")
                return []

            print("[PersonioAPI] Parsed XML structure")

            # Safely get workzag-jobs with proper None handling
            workzag_jobs = result.get("workzag-jobs") if result else None
            if workzag_jobs is None:
                print("[PersonioAPI] No 'workzag-jobs' element found in XML")
                return []

            # Safely get positions
            positions = workzag_jobs.get("position") if isinstance(workzag_jobs, dict) else None
            if positions is None:
                print("[PersonioAPI] No 'position' elements found in XML")
                return []

            # Ensure positions is a list
            if not isinstance(positions, list):
                positions = [positions] if positions else []

            jobs: List[PersonioJob] = []
            for pos in positions:
                if not isinstance(pos, dict):
                    continue

                # Parse additional offices with safe None handling
                additional_offices: List[str] = []
                additional_offices_data = pos.get("additionalOffices")
                if additional_offices_data and isinstance(additional_offices_data, dict):
                    office_data = additional_offices_data.get("office")
                    if office_data:
                        if not isinstance(office_data, list):
                            office_data = [office_data]
                        additional_offices.extend(str(o) for o in office_data if o)

                # Get main office and combine with additional offices
                main_office = pos.get("office", "") or ""
                all_offices = [main_office] + additional_offices
                all_offices = [str(o).strip() for o in all_offices if o and str(o).strip()]

                # Parse job descriptions with safe None handling
                job_descriptions: List[JobDescription] = []
                job_descriptions_data = pos.get("jobDescriptions")
                if job_descriptions_data and isinstance(job_descriptions_data, dict):
                    description_data = job_descriptions_data.get("jobDescription")
                    if description_data:
                        if not isinstance(description_data, list):
                            description_data = [description_data]

                        for desc in description_data:
                            if isinstance(desc, dict):
                                name = desc.get("name")
                                value = desc.get("value")
                                if name and value:
                                    job_descriptions.append(
                                        JobDescription(
                                            name=str(name),
                                            value=self._clean_cdata(str(value)),
                                        )
                                    )

                # Build job data with safe defaults
                job_name = pos.get("name", "") or ""
                job_data = {
                    "id": str(pos.get("id", "")) if pos.get("id") else "",
                    "name": job_name,
                    "slug": self._create_slug(job_name),
                    "office": main_office,
                    "allOffices": all_offices,
                    "employmentType": pos.get("schedule") or pos.get("employmentType") or "",
                    "department": pos.get("department", "") or "",
                    "recruitingCategory": pos.get("recruitingCategory"),
                    "subcompany": pos.get("subcompany"),
                    "seniority": pos.get("seniority"),
                    "schedule": pos.get("schedule"),
                    "otherOffices": additional_offices if additional_offices else None,
                    "jobDescriptions": job_descriptions if job_descriptions else None,
                }

                jobs.append(PersonioJob(**job_data))

            print(f"[PersonioAPI] Parsed {len(jobs)} jobs from XML")
            return jobs
        except PersonioParseError:
            raise
        except Exception as e:
            error_msg = str(e)
            if "syntax error" in error_msg.lower() or "line 1, column 0" in error_msg:
                raise PersonioParseError(
                    f"Invalid or empty XML response: {error_msg}",
                    original_error=e if isinstance(e, Exception) else None
                )
            raise PersonioParseError(
                f"Failed to parse XML jobs feed: {error_msg}",
                original_error=e if isinstance(e, Exception) else None
            )

    def _parse_json_jobs(self, data: List[dict]) -> List[PersonioJob]:
        """Parse JSON job data."""
        print(f"[PersonioAPI] Parsing {len(data)} jobs from JSON")

        jobs: List[PersonioJob] = []
        for job_data in data:
            job_dict = {
                "id": job_data.get("id", ""),
                "name": job_data.get("name", ""),
                "slug": job_data.get("slug", ""),
                "office": job_data.get("office", ""),
                "allOffices": job_data.get("allOffices", [job_data.get("office", "")]),
                "employmentType": job_data.get("employmentType", ""),
                "department": job_data.get("department", ""),
                "compensation": job_data.get("compensation"),
                "createdAt": job_data.get("createdAt"),
                "otherOffices": job_data.get("otherOffices"),
            }
            jobs.append(PersonioJob(**job_dict))

        return jobs

    def get_all_jobs(self) -> List[PersonioJob]:
        """Fetch all job listings."""
        api_type = self._detect_api_type()

        if api_type == "json":
            return self._get_all_jobs_json()
        elif api_type == "search_json":
            return self._get_all_jobs_search_json()
        else:
            # For company subdomains, try search.json first (faster), then fall back to XML
            if ".jobs.personio." in self.base_url:
                try:
                    return self._get_all_jobs_search_json()
                except (PersonioAPIError, PersonioParseError):
                    # Fall back to XML if search.json fails
                    print("[PersonioAPI] search.json failed, falling back to XML...")
                    return self._get_all_jobs_xml()
            else:
                # For other URLs, use XML as detected
                return self._get_all_jobs_xml()

    def _get_all_jobs_json(self) -> List[PersonioJob]:
        """Fetch jobs from JSON API."""
        url = f"{self.base_url}/api/careers/jobs/list/"
        print(f"[PersonioAPI] Fetching jobs from JSON API: {url}")

        try:
            response = self._fetch_with_timeout(url)

            if response.status_code != 200:
                raise PersonioAPIError(
                    f"Failed to fetch jobs: {response.status_code} {response.reason}",
                    response.status_code
                )

            # Check content type
            content_type = response.headers.get("content-type", "").lower()
            if "html" in content_type and "json" not in content_type:
                raise PersonioParseError(
                    f"Received HTML instead of JSON (content-type: {content_type}). "
                    "This may indicate the JSON API is not available for this company."
                )

            # Check if response is empty
            if not response.text or not response.text.strip():
                print("[PersonioAPI] Empty JSON response received")
                return []

            try:
                data = response.json()
            except ValueError as e:
                raise PersonioParseError(
                    f"Failed to parse JSON response: {str(e)}. "
                    f"Response preview: {response.text[:200]}"
                )

            if data is None:
                print("[PersonioAPI] JSON response is None")
                return []

            if not isinstance(data, list):
                raise PersonioParseError(
                    f"Expected array of jobs, got {type(data).__name__}. "
                    f"Response preview: {str(data)[:200]}"
                )

            return self._parse_json_jobs(data)
        except PersonioAPIError:
            raise
        except PersonioParseError:
            raise
        except Exception as e:
            raise PersonioAPIError(
                f"Failed to fetch jobs from {url}: {str(e)}",
                original_error=e if isinstance(e, Exception) else None
            )

    def _parse_search_json_jobs(self, data: list) -> List[PersonioJob]:
        """Parse search.json job data format.
        
        Args:
            data: Array of job objects from search.json endpoint
        """
        if not isinstance(data, list):
            if data:
                data = [data]
            else:
                data = []

        print(f"[PersonioAPI] Parsing {len(data)} jobs from search.json")

        jobs: List[PersonioJob] = []
        for job_data in data:
            if not isinstance(job_data, dict):
                continue

            # Handle offices: search.json provides both 'office' (comma-separated string) and 'offices' (array)
            office_str = job_data.get("office", "") or ""
            offices_array = job_data.get("offices", [])
            
            # Parse comma-separated office string
            if office_str:
                office_list = [o.strip() for o in office_str.split(",") if o.strip()]
            else:
                office_list = []
            
            # Use offices array if available, otherwise use parsed office string
            if isinstance(offices_array, list) and offices_array:
                all_offices = [str(o).strip() for o in offices_array if o and str(o).strip()]
            else:
                all_offices = office_list
            
            # Use first office as primary office, or empty string if none
            primary_office = all_offices[0] if all_offices else ""

            # Handle job descriptions - store description if present
            job_descriptions = None
            description = job_data.get("description", "")
            if description and description.strip():
                job_descriptions = [
                    JobDescription(name="description", value=description.strip())
                ]

            # Map fields from search.json format to PersonioJob format
            job_dict = {
                "id": str(job_data.get("id", "")) if job_data.get("id") is not None else "",
                "name": job_data.get("name", "") or "",
                "slug": self._create_slug(job_data.get("name", "")),
                "office": primary_office,
                "allOffices": all_offices,
                "employmentType": job_data.get("employment_type", "") or "",
                "department": job_data.get("department", "") or "",
                "recruitingCategory": job_data.get("category"),  # Map 'category' to 'recruitingCategory'
                "subcompany": job_data.get("subcompany"),
                "seniority": job_data.get("seniority"),
                "schedule": job_data.get("schedule"),
                "compensation": job_data.get("compensation"),
                "createdAt": job_data.get("createdAt"),
                "otherOffices": None,  # search.json doesn't provide otherOffices separately
                "jobDescriptions": job_descriptions,
            }
            jobs.append(PersonioJob(**job_dict))

        return jobs

    def _get_all_jobs_search_json(self) -> List[PersonioJob]:
        """Fetch jobs from search.json endpoint."""
        url = f"{self.base_url}/search.json"
        print(f"[PersonioAPI] Fetching jobs from search.json API: {url}")

        try:
            response = self._fetch_with_timeout(url)

            if response.status_code != 200:
                raise PersonioAPIError(
                    f"Failed to fetch search.json: {response.status_code} {response.reason}",
                    response.status_code
                )

            # Check content type
            content_type = response.headers.get("content-type", "").lower()
            if "html" in content_type and "json" not in content_type:
                raise PersonioParseError(
                    f"Received HTML instead of JSON (content-type: {content_type}). "
                    "This may indicate the search.json endpoint is not available for this company."
                )

            # Check if response is empty
            if not response.text or not response.text.strip():
                print("[PersonioAPI] Empty search.json response received")
                return []

            try:
                data = response.json()
            except ValueError as e:
                raise PersonioParseError(
                    f"Failed to parse search.json response: {str(e)}. "
                    f"Response preview: {response.text[:200]}"
                )

            if data is None:
                print("[PersonioAPI] search.json response is None")
                return []

            if not isinstance(data, list):
                raise PersonioParseError(
                    f"Expected array of jobs, got {type(data).__name__}. "
                    f"Response preview: {str(data)[:200]}"
                )

            return self._parse_search_json_jobs(data)
        except PersonioAPIError:
            raise
        except PersonioParseError:
            raise
        except Exception as e:
            raise PersonioAPIError(
                f"Failed to fetch jobs from {url}: {str(e)}",
                original_error=e if isinstance(e, Exception) else None
            )

    def _get_all_jobs_xml(self) -> List[PersonioJob]:
        """Fetch jobs from XML feed."""
        url = f"{self.base_url}/xml"
        print(f"[PersonioAPI] Fetching jobs from XML feed: {url}")

        try:
            response = self._fetch_with_timeout(url)

            if response.status_code != 200:
                raise PersonioAPIError(
                    f"Failed to fetch XML feed: {response.status_code} {response.reason}",
                    response.status_code
                )

            # Check content type
            content_type = response.headers.get("content-type", "").lower()
            if "html" in content_type and "xml" not in content_type:
                raise PersonioParseError(
                    f"Received HTML instead of XML (content-type: {content_type}). "
                    "This may indicate the XML feed is not available for this company."
                )

            xml_text = response.text

            # Check if response is empty
            if not xml_text or not xml_text.strip():
                print("[PersonioAPI] Empty XML response received")
                return []

            return self._parse_xml_jobs(xml_text)
        except PersonioAPIError:
            raise
        except PersonioParseError:
            raise
        except Exception as e:
            raise PersonioAPIError(
                f"Failed to fetch jobs from {url}: {str(e)}",
                original_error=e if isinstance(e, Exception) else None
            )

    def get_offices(self) -> List[PersonioOffice]:
        """Get offices (JSON API only, or extracted from XML jobs)."""
        api_type = self._detect_api_type()

        if api_type == "xml":
            # For XML APIs, extract offices from job listings
            jobs = self._get_all_jobs_xml()
            office_set = set()
            for job in jobs:
                for office in job.all_offices:
                    office_set.add(office)
            return [PersonioOffice(name=name) for name in office_set]

        url = f"{self.base_url}/api/careers/offices/list/"
        print(f"[PersonioAPI] Fetching offices from: {url}")

        try:
            response = self._fetch_with_timeout(url)

            if response.status_code != 200:
                raise PersonioAPIError(
                    f"Failed to fetch offices: {response.status_code} {response.reason}",
                    response.status_code
                )

            data = response.json()

            if not isinstance(data, list):
                raise PersonioParseError(f"Expected array of offices, got {type(data)}")

            return [PersonioOffice(name=office) for office in data]
        except PersonioAPIError:
            raise
        except PersonioParseError:
            raise
        except Exception as e:
            raise PersonioAPIError(
                f"Failed to fetch offices: {str(e)}",
                original_error=e if isinstance(e, Exception) else None
            )

    def get_departments(self) -> List[PersonioDepartment]:
        """Get departments (JSON API only, or extracted from XML jobs)."""
        api_type = self._detect_api_type()

        if api_type == "xml":
            # For XML APIs, extract departments from job listings
            jobs = self._get_all_jobs_xml()
            department_set = set()
            for job in jobs:
                if job.department:
                    department_set.add(job.department)
            return [PersonioDepartment(name=name) for name in department_set]

        url = f"{self.base_url}/api/careers/departments/list/"
        print(f"[PersonioAPI] Fetching departments from: {url}")

        try:
            response = self._fetch_with_timeout(url)

            if response.status_code != 200:
                raise PersonioAPIError(
                    f"Failed to fetch departments: {response.status_code} {response.reason}",
                    response.status_code
                )

            data = response.json()

            if not isinstance(data, list):
                raise PersonioParseError(f"Expected array of departments, got {type(data)}")

            return [PersonioDepartment(name=dept) for dept in data]
        except PersonioAPIError:
            raise
        except PersonioParseError:
            raise
        except Exception as e:
            raise PersonioAPIError(
                f"Failed to fetch departments: {str(e)}",
                original_error=e if isinstance(e, Exception) else None
            )

    def get_job_by_id(self, job_id: str) -> Optional[PersonioJob]:
        """Get a specific job by ID."""
        print(f"[PersonioAPI] Finding job by ID: {job_id}")
        jobs = self.get_all_jobs()
        for job in jobs:
            if job.id == job_id:
                return job
        return None

    def filter_jobs(
        self,
        office: Optional[str] = None,
        department: Optional[str] = None,
        employment_type: Optional[str] = None,
        recruiting_category: Optional[str] = None,
    ) -> List[PersonioJob]:
        """Filter jobs by criteria."""
        print(f"[PersonioAPI] Filtering jobs with criteria: office={office}, department={department}, employment_type={employment_type}, recruiting_category={recruiting_category}")
        jobs = self.get_all_jobs()

        if office:
            office_lower = office.lower()
            jobs = [
                job for job in jobs
                if office_lower in job.office.lower() or
                any(office_lower in loc.lower() for loc in job.all_offices)
            ]

        if department:
            dept_lower = department.lower()
            jobs = [job for job in jobs if dept_lower in job.department.lower()]

        if employment_type:
            type_lower = employment_type.lower()
            jobs = [job for job in jobs if type_lower in job.employment_type.lower()]

        if recruiting_category:
            category_lower = recruiting_category.lower()
            jobs = [
                job for job in jobs
                if job.recruiting_category and category_lower in job.recruiting_category.lower()
            ]

        print(f"[PersonioAPI] Filtered to {len(jobs)} jobs")
        return jobs

    def get_job_url(self, job: PersonioJob) -> str:
        """Get the full URL to a job posting."""
        if job.slug:
            return f"{self.base_url}/careers/{job.id}/{job.slug}"
        return f"{self.base_url}/careers/{job.id}"

    def close(self):
        """Close the session and clean up resources."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
