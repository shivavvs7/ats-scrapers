# Mercor API Client

This directory contains a reverse-engineered API client for fetching job listings from [Mercor](https://work.mercor.com/).

## Captured APIs

The following API endpoint was discovered and implemented:

### 1. Get Job Listings
- **URL**: `https://aws.api.mercor.com/work/listings-explore-page`
- **Method**: `GET`
- **Authentication**: Requires an `Authorization: Bearer` header (token value appears to be empty/optional for public explore page).
- **Description**: Returns a JSON object containing a list of all active job listings currently displayed on the Mercor explore page. Each listing includes title, company name, rate, location, and description.

## Usage

### Prerequisites
- Python 3.x
- `requests` library

### Installation
```bash
pip install requests
```

### Example
```python
from api_client import MercorClient

client = MercorClient()
jobs = client.get_job_listings()

for job in jobs:
    print(f"{job['title']} @ {job['companyName']}")
```

## Authentication Note
The captured traffic showed that requests to the explore page use a `Bearer` token with an empty value. This client replicates that behavior. If a real token is required for private listings in the future, it can be passed in the headers.

## Directory Structure
- `api_client.py`: The Python client implementation.
- `README.md`: This documentation file.
