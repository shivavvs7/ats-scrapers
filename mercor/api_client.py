import requests
import logging
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MercorAPIError(Exception):
    """Base exception for Mercor API errors."""

    pass


class MercorClient:
    """
    A client to interact with Mercor's job API.
    """

    BASE_URL = "https://aws.api.mercor.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "accept": "application/json, text/plain, */*",
                "accept-language": "en-US,en;q=0.9",
                "authorization": "Bearer",
                "origin": "https://work.mercor.com",
                "referer": "https://work.mercor.com/",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
                "x-client-ip": "true",
            }
        )

    def get_job_listings(self) -> List[Dict[str, Any]]:
        """
        Fetches all job listings from the explore page.

        Returns:
            List[Dict[str, Any]]: A list of job listings.

        Raises:
            MercorAPIError: If the API request fails.
        """
        url = f"{self.BASE_URL}/work/listings-explore-page"
        try:
            logger.info(f"Fetching job listings from {url}")
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            listings = data.get("listings", [])
            logger.info(f"Successfully fetched {len(listings)} listings")
            return listings
        except requests.RequestException as e:
            logger.error(f"Failed to fetch job listings: {e}")
            raise MercorAPIError(f"API request failed: {e}")
        except ValueError as e:
            logger.error(f"Failed to parse API response: {e}")
            raise MercorAPIError(f"Invalid JSON response: {e}")

    def get_job_details(self, listing_id: str) -> Optional[Dict[str, Any]]:
        """
        Finds a specific job listing by its ID from the fetched listings.
        Note: The current API captured returns all listings on the explore page.

        Args:
            listing_id: The ID of the job listing.

        Returns:
            Optional[Dict[str, Any]]: The job listing details if found, else None.
        """
        listings = self.get_job_listings()
        for listing in listings:
            if listing.get("listingId") == listing_id:
                return listing
        return None


if __name__ == "__main__":
    client = MercorClient()
    try:
        jobs = client.get_job_listings()
        print(f"Found {len(jobs)} jobs.")
        if jobs:
            print(f"First job: {jobs[0].get('title')} at {jobs[0].get('companyName')}")
    except MercorAPIError as e:
        print(f"Error: {e}")
