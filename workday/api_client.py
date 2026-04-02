"""
Workday Job Board API Client

A production-ready Python client for scraping job postings from any Workday-powered
career site. This client handles authentication, session management, and provides
a clean interface for searching and retrieving job listings.

Author: Reverse-engineered from HAR file analysis
Date: 2025-12-26
"""

import json
import re
import time
from typing import Dict, List, Optional, Any, Iterator
from dataclasses import dataclass
from urllib.parse import urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class JobPosting:
    """Represents a single job posting from Workday"""
    title: str
    external_path: str
    posted_on: str
    bullet_fields: List[str]
    career_site_url: str = ""

    @property
    def job_id(self) -> str:
        """Extract job ID from bullet fields (usually first field)"""
        return self.bullet_fields[0] if self.bullet_fields else ""

    @property
    def location(self) -> str:
        """Extract location from bullet fields (usually second field)"""
        return self.bullet_fields[1] if len(self.bullet_fields) > 1 else ""

    @property
    def url(self) -> str:
        """Get the full URL to the job posting"""
        if self.career_site_url:
            return f"{self.career_site_url}{self.external_path}"
        return self.external_path

    def to_dict(self) -> Dict[str, Any]:
        """Convert job posting to dictionary"""
        return {
            "title": self.title,
            "external_path": self.external_path,
            "posted_on": self.posted_on,
            "job_id": self.job_id,
            "location": self.location,
            "url": self.url,
            "bullet_fields": self.bullet_fields
        }


class WorkdayAPIClient:
    """
    Client for interacting with Workday job board APIs.

    This client works with any company using Workday for their career site.
    It handles authentication, session management, and provides methods for
    searching and retrieving job postings.

    Example:
        >>> client = WorkdayAPIClient("https://accenture.wd103.myworkdayjobs.com/accenturecareers")
        >>> jobs = client.search_jobs(search_text="python developer", limit=50)
        >>> for job in jobs:
        ...     print(f"{job.title} - {job.location}")
    """

    def __init__(self, career_site_url: str, timeout: int = 30):
        """
        Initialize the Workday API client.

        Args:
            career_site_url: The full URL to the company's Workday career site
                           (e.g., "https://company.wd103.myworkdayjobs.com/careers")
            timeout: Request timeout in seconds (default: 30)

        Raises:
            ValueError: If the career site URL is invalid
        """
        self.career_site_url = career_site_url.rstrip('/')
        self.timeout = timeout

        # Parse URL to extract components
        self._parse_url()

        # Session management
        self.session = self._create_session()
        self._authenticated = False
        self._cookies: Dict[str, str] = {}
        self._csrf_token: Optional[str] = None

    def _parse_url(self) -> None:
        """Parse the career site URL to extract API components"""
        parsed = urlparse(self.career_site_url)

        # Extract domain (e.g., accenture.wd103.myworkdayjobs.com)
        self.domain = parsed.netloc

        # Extract path components (e.g., /accenturecareers or /company/sitename)
        path_parts = [p for p in parsed.path.split('/') if p]

        if not path_parts:
            raise ValueError(f"Invalid Workday URL: {self.career_site_url}. Expected format: https://company.wdXXX.myworkdayjobs.com/sitename")

        # For Workday URLs, the pattern is typically:
        # https://{company}.{instance}.myworkdayjobs.com/{site_name}
        # API path: /wday/cxs/{company}/{site_name}/jobs

        # Extract company name from domain
        company_match = re.match(r'^([^.]+)\.', self.domain)
        if not company_match:
            raise ValueError(f"Could not extract company from domain: {self.domain}")

        self.company_name = company_match.group(1)
        self.site_name = path_parts[-1]  # Last part of path is site name

        # Build API URL
        self.api_base_url = f"https://{self.domain}/wday/cxs/{self.company_name}/{self.site_name}"

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic and proper headers"""
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        # Set default headers to mimic a real browser
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
        })

        return session

    def _initialize_session(self) -> None:
        """
        Initialize session by loading the career site page to get cookies and CSRF token.

        This mimics the browser behavior of visiting the career page first,
        which sets up the necessary cookies and tokens for API requests.
        """
        if self._authenticated:
            return

        try:
            # Make initial GET request to career site
            response = self.session.get(
                self.career_site_url,
                timeout=self.timeout,
                headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'sec-fetch-dest': 'document',
                    'sec-fetch-mode': 'navigate',
                    'sec-fetch-site': 'none',
                    'sec-fetch-user': '?1',
                    'upgrade-insecure-requests': '1',
                }
            )
            response.raise_for_status()

            # Extract CSRF token from response headers
            self._csrf_token = response.headers.get('x-calypso-csrf-token')

            # Store cookies
            self._cookies = dict(self.session.cookies)

            # If CSRF token is also in cookies, use that
            if 'CALYPSO_CSRF_TOKEN' in self._cookies:
                self._csrf_token = self._cookies['CALYPSO_CSRF_TOKEN']

            if not self._csrf_token:
                raise Exception("Failed to obtain CSRF token from initial request")

            self._authenticated = True

        except requests.RequestException as e:
            raise Exception(f"Failed to initialize session: {str(e)}")

    def search_jobs(
        self,
        search_text: str = "",
        applied_facets: Optional[Dict[str, List[str]]] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[JobPosting]:
        """
        Search for job postings.

        Args:
            search_text: Free-text search query (default: "")
            applied_facets: Filters to apply (e.g., {"location": ["New York"], "jobFamily": ["Engineering"]})
            limit: Maximum number of results to return (default: 20)
            offset: Number of results to skip for pagination (default: 0)

        Returns:
            List of JobPosting objects

        Raises:
            Exception: If the API request fails
        """
        # Initialize session if not already done
        if not self._authenticated:
            self._initialize_session()

        # Build request payload
        payload = {
            "appliedFacets": applied_facets or {},
            "limit": limit,
            "offset": offset,
            "searchText": search_text
        }

        # Build API URL
        api_url = f"{self.api_base_url}/jobs"

        # Set headers including CSRF token
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Origin': f"https://{self.domain}",
            'Referer': self.career_site_url,
            'x-calypso-csrf-token': self._csrf_token,
        }

        try:
            # Make POST request to jobs API
            response = self.session.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()

            # Parse job postings
            jobs = []
            for job_data in data.get('jobPostings', []):
                job = JobPosting(
                    title=job_data.get('title', ''),
                    external_path=job_data.get('externalPath', ''),
                    posted_on=job_data.get('postedOn', ''),
                    bullet_fields=job_data.get('bulletFields', []),
                    career_site_url=self.career_site_url
                )
                jobs.append(job)

            return jobs

        except requests.RequestException as e:
            raise Exception(f"Failed to search jobs: {str(e)}")

    def get_all_jobs(
        self,
        search_text: str = "",
        applied_facets: Optional[Dict[str, List[str]]] = None,
        max_results: Optional[int] = None,
        delay_between_requests: float = 0.5
    ) -> Iterator[JobPosting]:
        """
        Get all job postings by automatically handling pagination.

        This is a generator that yields jobs one at a time, fetching new pages as needed.

        Args:
            search_text: Free-text search query (default: "")
            applied_facets: Filters to apply
            max_results: Maximum total results to fetch (default: None = all)
            delay_between_requests: Delay in seconds between page requests to be respectful (default: 0.5)

        Yields:
            JobPosting objects one at a time

        Example:
            >>> client = WorkdayAPIClient("https://company.wd103.myworkdayjobs.com/careers")
            >>> for job in client.get_all_jobs(search_text="python", max_results=100):
            ...     print(job.title)
        """
        # Get total count first to know when to stop
        total_available = self.get_total_count(search_text=search_text, applied_facets=applied_facets)

        offset = 0
        page_size = 20
        total_fetched = 0
        seen_job_ids = set()  # Track unique jobs to detect duplicates

        while True:
            # Check if we've hit the max_results limit
            if max_results and total_fetched >= max_results:
                break

            # Check if we've fetched all available jobs
            if total_fetched >= total_available:
                break

            # Fetch next page
            jobs = self.search_jobs(
                search_text=search_text,
                applied_facets=applied_facets,
                limit=page_size,
                offset=offset
            )

            # If no jobs returned, we've reached the end
            if not jobs:
                break

            # Check for duplicates (API might return same jobs)
            new_jobs_found = False
            for job in jobs:
                # Create unique ID from external_path
                job_id = job.external_path

                # Skip if we've seen this job before (duplicate detection)
                if job_id in seen_job_ids:
                    continue

                seen_job_ids.add(job_id)
                new_jobs_found = True

                if max_results and total_fetched >= max_results:
                    break

                yield job
                total_fetched += 1

            # If no new jobs found on this page, we're getting duplicates - stop
            if not new_jobs_found:
                break

            # Move to next page
            offset += page_size

            # Be respectful - add delay between requests
            if jobs:  # Only delay if we got results and will continue
                time.sleep(delay_between_requests)

    def get_all_jobs_unlimited(
        self,
        search_text: str = "",
        max_results: Optional[int] = None,
        delay_between_requests: float = 0.5,
        max_per_facet: int = 1500  # Stay under 2000 limit with safety margin
    ) -> Iterator[JobPosting]:
        """
        Get all job postings, automatically using facets to work around the 2000 result limit.

        Workday's API has a hard limit of 2000 results per search. This method automatically
        subdivides searches using available facets (location, job family, etc.) when the
        total count exceeds the limit.

        Args:
            search_text: Free-text search query (default: "")
            max_results: Maximum total results to fetch (default: None = all)
            delay_between_requests: Delay in seconds between page requests (default: 0.5)
            max_per_facet: Maximum jobs per facet combination (default: 1500)

        Yields:
            JobPosting objects one at a time

        Example:
            >>> client = WorkdayAPIClient("https://company.wd103.myworkdayjobs.com/careers")
            >>> for job in client.get_all_jobs_unlimited(max_results=5000):
            ...     print(job.title)
        """
        WORKDAY_HARD_LIMIT = 2000

        # First, check total count without any facets
        total_available = self.get_total_count(search_text=search_text)

        # If under the limit, use regular get_all_jobs
        if total_available <= WORKDAY_HARD_LIMIT:
            yield from self.get_all_jobs(
                search_text=search_text,
                max_results=max_results,
                delay_between_requests=delay_between_requests
            )
            return

        # Need to use facets - get available facets
        print(f"  Total jobs ({total_available}) exceeds 2000 limit. Using facets to subdivide...")
        facets = self.get_facets(search_text=search_text)

        # Build facet combinations to try
        facet_combinations = self._build_facet_combinations(
            facets, search_text, max_per_facet
        )

        print(f"  Will fetch using {len(facet_combinations)} facet combinations")

        # Track seen jobs for deduplication
        seen_job_ids = set()
        total_fetched = 0

        for i, facet_combo in enumerate(facet_combinations, 1):
            # Check if we've hit the max_results limit
            if max_results and total_fetched >= max_results:
                break

            # Extract search text from combo (for alphabetical splits)
            combo_search_text = search_text
            combo_facets = facet_combo
            if "_search" in facet_combo:
                combo_search_text = facet_combo["_search"]
                combo_facets = {k: v for k, v in facet_combo.items() if k != "_search"}

            # Get count for this facet combination
            combo_count = self.get_total_count(
                search_text=combo_search_text,
                applied_facets=combo_facets if combo_facets else None
            )

            if combo_count == 0:
                continue

            # Skip if this combo still exceeds limit (shouldn't happen if _build_facet_combinations works)
            if combo_count > WORKDAY_HARD_LIMIT:
                combo_display = combo_search_text[:20] if combo_search_text else str(combo_facets)[:40]
                print(f"    Warning: Combo '{combo_display}' has {combo_count} jobs, may be truncated")

            # Calculate remaining jobs to fetch
            remaining = None
            if max_results:
                remaining = max_results - total_fetched
                if remaining <= 0:
                    break

            combo_display = combo_search_text[:20] if combo_search_text else str(combo_facets)[:40]
            print(f"    Fetching combo {i}/{len(facet_combinations)}: {combo_display}... ({combo_count} jobs)")

            # Fetch jobs for this facet combination
            for job in self.get_all_jobs(
                search_text=combo_search_text,
                applied_facets=combo_facets if combo_facets else None,
                max_results=remaining,
                delay_between_requests=delay_between_requests
            ):
                # Deduplicate
                job_id = job.external_path
                if job_id in seen_job_ids:
                    continue

                seen_job_ids.add(job_id)
                yield job
                total_fetched += 1

                if max_results and total_fetched >= max_results:
                    break

            # Small delay between facet combinations
            if i < len(facet_combinations):
                time.sleep(delay_between_requests)

    def _build_facet_combinations(
        self,
        facets: List[Any],
        search_text: str,
        max_per_facet: int
    ) -> List[Dict[str, List[str]]]:
        """
        Build facet combinations to subdivide large result sets.
        
        Uses aggressive multi-level facet subdivision to get as close to 100% coverage
        as possible given Workday's 2000 result limit.

        Returns a list of applied_facets dictionaries that should each return
        fewer than max_per_facet results.
        """
        WORKDAY_HARD_LIMIT = 2000
        # Use 800 instead of 1500 to be more aggressive about subdivision
        # This creates more API calls but captures more jobs
        target_max = min(max_per_facet, 800)
        
        facet_combinations = []

        # Extract facet values by type
        countries = []
        states = []
        job_families = []
        time_types = []
        worker_subtypes = []
        locations = []

        for facet in facets:
            facet_id = facet.get('facetParameter', '') or facet.get('id', '')
            facet_name = facet.get('descriptor', '') or facet.get('name', '')
            values = facet.get('values', [])

            if 'Location_Country' in facet_id:
                countries = [(v.get('id'), v.get('descriptor', v.get('value', '')), v.get('count', 0)) for v in values if v.get('id')]
            elif 'Location_Region_State' in facet_id:
                states = [(v.get('id'), v.get('descriptor', v.get('value', '')), v.get('count', 0)) for v in values if v.get('id')]
            elif 'jobFamily' in facet_id or 'Job Family' in facet_name or 'Job Category' in facet_name:
                job_families = [(v.get('id'), v.get('descriptor', v.get('value', '')), v.get('count', 0)) for v in values if v.get('id')]
            elif 'timeType' in facet_id or 'Full/Part' in facet_name:
                time_types = [(v.get('id'), v.get('descriptor', v.get('value', '')), v.get('count', 0)) for v in values if v.get('id')]
            elif 'workerSubType' in facet_id or 'Job Type' in facet_name:
                worker_subtypes = [(v.get('id'), v.get('descriptor', v.get('value', '')), v.get('count', 0)) for v in values if v.get('id')]
            elif 'Location' in facet_id and not 'Country' in facet_id and not 'State' in facet_id:
                locations = [(v.get('id'), v.get('descriptor', v.get('value', '')), v.get('count', 0)) for v in values if v.get('id')]

        # AGGRESSIVE STRATEGY: Always use the most granular subdivision possible
        # Try: Job Family + Time Type + Worker SubType combinations first
        if job_families:
            print(f"    Building {len(job_families)} job family combinations...")
            
            for jf_id, jf_name, jf_count in job_families:
                if jf_count == 0:
                    continue
                    
                if jf_count <= target_max:
                    # Small enough, add as-is
                    facet_combinations.append({"jobFamilyGroup": [jf_id]})
                else:
                    # Large job family - get time types for this family
                    jf_time_types = self._get_facet_values_for_job_family(search_text, jf_id, "timeType")
                    
                    if jf_time_types:
                        for tt_id, tt_name, tt_count in jf_time_types:
                            if tt_count == 0:
                                continue
                            if tt_count <= target_max:
                                facet_combinations.append({
                                    "jobFamilyGroup": [jf_id],
                                    "timeType": [tt_id]
                                })
                            else:
                                # Still too big - add worker subtype
                                jf_tt_subtypes = self._get_facet_values_for_job_family_time(
                                    search_text, jf_id, tt_id, "workerSubType"
                                )
                                if jf_tt_subtypes:
                                    for st_id, st_name, st_count in jf_tt_subtypes:
                                        if st_count == 0:
                                            continue
                                        if st_count <= target_max:
                                            facet_combinations.append({
                                                "jobFamilyGroup": [jf_id],
                                                "timeType": [tt_id],
                                                "workerSubType": [st_id]
                                            })
                                        else:
                                            # Still too big - use alphabetical
                                            alpha_splits = self._build_alphabetical_splits(
                                                search_text, 
                                                {"jobFamilyGroup": [jf_id], "timeType": [tt_id], "workerSubType": [st_id]},
                                                target_max
                                            )
                                            facet_combinations.extend(alpha_splits)
                                else:
                                    # No subtypes, add as-is
                                    facet_combinations.append({
                                        "jobFamilyGroup": [jf_id],
                                        "timeType": [tt_id]
                                    })
                    else:
                        # No time types, try alphabetical
                        alpha_splits = self._build_alphabetical_splits(
                            search_text, {"jobFamilyGroup": [jf_id]}, target_max
                        )
                        facet_combinations.extend(alpha_splits)
        
        # If no job families, try location-based subdivision
        elif countries:
            print(f"    Using {len(countries)} country combinations...")
            for country_id, country_name, count in countries:
                if count == 0:
                    continue
                if count <= target_max:
                    facet_combinations.append({"Location_Country": [country_id]})
                else:
                    # Get states for this country
                    country_states = self._get_facet_values_for_country(
                        search_text, country_id, "Location_Region_State_Province"
                    )
                    if country_states:
                        for state_id, state_name, state_count in country_states:
                            if state_count <= target_max:
                                facet_combinations.append({
                                    "Location_Country": [country_id],
                                    "Location_Region_State_Province": [state_id]
                                })
                            else:
                                # State too big, try alphabetical
                                alpha_splits = self._build_alphabetical_splits(
                                    search_text,
                                    {"Location_Country": [country_id], "Location_Region_State_Province": [state_id]},
                                    target_max
                                )
                                facet_combinations.extend(alpha_splits)
                    else:
                        facet_combinations.append({"Location_Country": [country_id]})
        
        # If no location or job families, try time type + worker subtype
        elif time_types:
            print(f"    Using {len(time_types)} time type combinations...")
            for tt_id, tt_name, tt_count in time_types:
                if tt_count <= target_max:
                    facet_combinations.append({"timeType": [tt_id]})
                else:
                    # Get worker subtypes for this time type
                    tt_subtypes = self._get_facet_values_for_facet(search_text, {"timeType": [tt_id]}, "workerSubType")
                    if tt_subtypes:
                        for st_id, st_name, st_count in tt_subtypes:
                            if st_count <= target_max:
                                facet_combinations.append({
                                    "timeType": [tt_id],
                                    "workerSubType": [st_id]
                                })
                            else:
                                facet_combinations.append({
                                    "timeType": [tt_id],
                                    "workerSubType": [st_id]
                                })
                    else:
                        facet_combinations.append({"timeType": [tt_id]})
        
        # Last resort: alphabetical splitting on everything
        else:
            print("    No facets available, using alphabetical search...")
            alpha_splits = self._build_alphabetical_splits(search_text, {}, target_max)
            facet_combinations.extend(alpha_splits)

        # Deduplicate combinations
        seen = set()
        unique_combinations = []
        for combo in facet_combinations:
            combo_key = json.dumps(combo, sort_keys=True)
            if combo_key not in seen:
                seen.add(combo_key)
                unique_combinations.append(combo)
        
        facet_combinations = unique_combinations

        # Report oversized combinations
        oversized_count = 0
        for combo in facet_combinations:
            check_facets = {k: v for k, v in combo.items() if not k.startswith('_')}
            check_search = combo.get('_search', search_text)
            
            count = self.get_total_count(search_text=check_search, applied_facets=check_facets if check_facets else None)
            if count > 2000:
                oversized_count += 1
                if oversized_count <= 3:
                    combo_str = check_search[:15] if check_search else str(list(check_facets.keys()))[:30]
                    print(f"    ⚠ Combo '{combo_str}' has {count} jobs, will be truncated")
        
        if oversized_count > 3:
            print(f"    ... and {oversized_count - 3} more oversized combos")

        return facet_combinations

    def _get_facet_values_for_country(
        self,
        search_text: str,
        country_id: str,
        facet_id: str
    ) -> List[tuple]:
        """Get facet values for a specific country. Returns list of (id, descriptor, count) tuples."""
        facets = self.get_facets(
            search_text=search_text,
            applied_facets={"Location_Country": [country_id]}
        )

        for facet in facets:
            facet_param = facet.get('facetParameter', '') or facet.get('id', '')
            if facet_param == facet_id:
                values = facet.get('values', [])
                return [(v.get('id'), v.get('descriptor', v.get('value', '')), v.get('count', 0)) for v in values if v.get('id')]

        return []

    def _get_facet_values_for_state(
        self,
        search_text: str,
        country_id: str,
        state_id: str,
        facet_id: str
    ) -> List[tuple]:
        """Get facet values for a specific state within a country. Returns list of (id, descriptor, count) tuples."""
        facets = self.get_facets(
            search_text=search_text,
            applied_facets={
                "Location_Country": [country_id],
                "Location_Region_State_Province": [state_id]
            }
        )

        for facet in facets:
            facet_param = facet.get('facetParameter', '') or facet.get('id', '')
            if facet_param == facet_id:
                values = facet.get('values', [])
                return [(v.get('id'), v.get('descriptor', v.get('value', '')), v.get('count', 0)) for v in values if v.get('id')]

        return []

    def _get_facet_values_for_facet(
        self,
        search_text: str,
        applied_facets: Dict[str, List[str]],
        facet_id: str
    ) -> List[tuple]:
        """Get facet values for a specific facet filter. Returns list of (id, descriptor, count) tuples."""
        facets = self.get_facets(
            search_text=search_text,
            applied_facets=applied_facets
        )

        for facet in facets:
            facet_param = facet.get('facetParameter', '') or facet.get('id', '')
            if facet_param == facet_id:
                values = facet.get('values', [])
                return [(v.get('id'), v.get('descriptor', v.get('value', '')), v.get('count', 0)) for v in values if v.get('id')]

        return []

    def _get_facet_values_for_job_family(
        self,
        search_text: str,
        job_family_id: str,
        facet_id: str
    ) -> List[tuple]:
        """Get facet values for a specific job family. Returns list of (id, descriptor, count) tuples."""
        facets = self.get_facets(
            search_text=search_text,
            applied_facets={"jobFamilyGroup": [job_family_id]}
        )

        for facet in facets:
            facet_param = facet.get('facetParameter', '') or facet.get('id', '')
            if facet_param == facet_id:
                values = facet.get('values', [])
                return [(v.get('id'), v.get('descriptor', v.get('value', '')), v.get('count', 0)) for v in values if v.get('id')]

        return []

    def _build_alphabetical_splits(
        self,
        search_text: str,
        base_facets: Dict[str, List[str]],
        max_per_facet: int,
        max_letters: int = 15
    ) -> List[Dict[str, List[str]]]:
        """
        Build alphabetical search splits for large facet combinations.
        
        Uses searchText with letter prefixes to break down large result sets.
        For letters with >2000 jobs, also tries common two-letter prefixes.
        """
        import string
        
        combinations = []
        
        # Common two-letter prefixes for English words (covers ~80% of words)
        common_prefixes = [
            'th', 'he', 'in', 'er', 'an', 're', 'on', 'at', 'en', 'nd',
            'ti', 'es', 'or', 'te', 'of', 'ed', 'is', 'it', 'al', 'ar',
            'st', 'to', 'nt', 'ng', 'se', 'ha', 'as', 'ou', 'io', 'le',
            'sa', 've', 'ro', 'ra', 'hi', 'ne', 'me', 'de', 'co', 'ta',
            'ec', 'si', 'll', 'na', 'sh', 'ho', 'tt', 'fr', 'ee', 'ad'
        ]
        
        # Try single letters first
        letters_with_jobs = 0
        for letter in string.ascii_lowercase:
            if letters_with_jobs >= max_letters:
                print(f"      Stopping after {max_letters} letters")
                break
                
            count = self.get_total_count(search_text=letter, applied_facets=base_facets)
            
            if count == 0:
                continue
            
            letters_with_jobs += 1
            
            if count <= max_per_facet:
                # This letter is small enough
                combinations.append({**base_facets, "_search": letter})
            elif count > 2000:
                # Letter too big - try two-letter prefixes for this letter
                print(f"      Letter '{letter}' has {count} jobs, trying two-letter prefixes...")
                two_letter_found = False
                
                for prefix in common_prefixes:
                    if prefix.startswith(letter):
                        prefix_count = self.get_total_count(search_text=prefix, applied_facets=base_facets)
                        if prefix_count > 0:
                            two_letter_found = True
                            if prefix_count <= max_per_facet:
                                combinations.append({**base_facets, "_search": prefix})
                            else:
                                combinations.append({**base_facets, "_search": prefix})
                
                if not two_letter_found:
                    # No two-letter prefixes worked, just use the letter
                    combinations.append({**base_facets, "_search": letter})
            else:
                # Between max_per_facet and 2000
                combinations.append({**base_facets, "_search": letter})
        
        if not combinations:
            # No letters worked, just return the base facets
            combinations.append(base_facets)
        
        return combinations

    def _get_facet_values_for_job_family_time(
        self,
        search_text: str,
        job_family_id: str,
        time_type_id: str,
        facet_id: str
    ) -> List[tuple]:
        """Get facet values for a specific job family + time type. Returns list of (id, descriptor, count) tuples."""
        facets = self.get_facets(
            search_text=search_text,
            applied_facets={
                "jobFamilyGroup": [job_family_id],
                "timeType": [time_type_id]
            }
        )

        for facet in facets:
            facet_param = facet.get('facetParameter', '') or facet.get('id', '')
            if facet_param == facet_id:
                values = facet.get('values', [])
                return [(v.get('id'), v.get('descriptor', v.get('value', '')), v.get('count', 0)) for v in values if v.get('id')]

        return []

    def get_total_count(
        self,
        search_text: str = "",
        applied_facets: Optional[Dict[str, List[str]]] = None
    ) -> int:
        """
        Get the total count of jobs matching the search criteria without fetching all jobs.

        Args:
            search_text: Free-text search query
            applied_facets: Filters to apply

        Returns:
            Total number of matching jobs
        """
        # Initialize session if not already done
        if not self._authenticated:
            self._initialize_session()

        # Build request payload with limit=1 to minimize data transfer
        payload = {
            "appliedFacets": applied_facets or {},
            "limit": 1,
            "offset": 0,
            "searchText": search_text
        }

        # Build API URL
        api_url = f"{self.api_base_url}/jobs"

        # Set headers
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Origin': f"https://{self.domain}",
            'Referer': self.career_site_url,
            'x-calypso-csrf-token': self._csrf_token,
        }

        try:
            response = self.session.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            return data.get('total', 0)

        except requests.RequestException as e:
            raise Exception(f"Failed to get job count: {str(e)}")

    def get_facets(
        self,
        search_text: str = "",
        applied_facets: Optional[Dict[str, List[str]]] = None
    ) -> List[Any]:
        """
        Get available facets (filters) for the current search.

        Args:
            search_text: Free-text search query
            applied_facets: Currently applied filters

        Returns:
            List of available facets/filters
        """
        # Initialize session if not already done
        if not self._authenticated:
            self._initialize_session()

        # Build request payload
        payload = {
            "appliedFacets": applied_facets or {},
            "limit": 1,
            "offset": 0,
            "searchText": search_text
        }

        # Build API URL
        api_url = f"{self.api_base_url}/jobs"

        # Set headers
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Origin': f"https://{self.domain}",
            'Referer': self.career_site_url,
            'x-calypso-csrf-token': self._csrf_token,
        }

        try:
            response = self.session.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            return data.get('facets', [])

        except requests.RequestException as e:
            raise Exception(f"Failed to get facets: {str(e)}")

    def close(self) -> None:
        """Close the session"""
        self.session.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


def main():
    """Example usage of the Workday API client"""

    # Example 1: Search Accenture jobs
    print("=" * 80)
    print("Example 1: Searching Accenture jobs for 'developer'")
    print("=" * 80)

    with WorkdayAPIClient("https://accenture.wd103.myworkdayjobs.com/accenturecareers") as client:
        # Get total count first
        total = client.get_total_count(search_text="developer")
        print(f"\nTotal jobs matching 'developer': {total}")

        # Search for jobs
        jobs = client.search_jobs(search_text="developer", limit=5)

        print(f"\nShowing first {len(jobs)} jobs:")
        for i, job in enumerate(jobs, 1):
            print(f"\n{i}. {job.title}")
            print(f"   Job ID: {job.job_id}")
            print(f"   Location: {job.location}")
            print(f"   Posted: {job.posted_on}")
            print(f"   URL: {job.url}")

    # Example 2: Get all jobs with pagination
    print("\n" + "=" * 80)
    print("Example 2: Getting all jobs (with pagination)")
    print("=" * 80)

    # Note: Change the URL to match your target company
    # This works with ANY Workday-powered career site!

    # You can also try other companies:
    # - https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
    # - https://google.wd5.myworkdayjobs.com/careers
    # - https://microsoft.wd5.myworkdayjobs.com/careers

    with WorkdayAPIClient("https://accenture.wd103.myworkdayjobs.com/accenturecareers") as client:
        print("\nFetching first 10 jobs:")
        for i, job in enumerate(client.get_all_jobs(max_results=10), 1):
            print(f"{i}. {job.title} - {job.location}")


if __name__ == "__main__":
    main()
