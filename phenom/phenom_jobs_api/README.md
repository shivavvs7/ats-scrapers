# Phenom Jobs API Client

A Python client for interacting with Phenom-powered career sites. This client allows you to programmatically search and retrieve job listings from companies that use Phenom's recruitment platform.

## Supported Companies

This API client works with any company using Phenom's career platform, including:

- **Bell Canada** (jobs.bell.ca)
- **GE Healthcare** (careers.gehealthcare.com)
- And hundreds of other companies worldwide

## Features

- ✅ Search jobs by keywords, location, and category
- ✅ Automatic pagination to retrieve all job listings
- ✅ Filter by multiple criteria
- ✅ Get detailed job information
- ✅ Session management with automatic CSRF token handling
- ✅ Type hints and comprehensive docstrings

## Installation

No external dependencies required beyond the Python standard library and `requests`:

```bash
pip install requests
```

## How It Works

### API Discovery

The Phenom platform uses a unified API across all companies. The main endpoint is:

```
POST /widgets
```

This endpoint handles various types of requests based on the `ddoKey` parameter:

- `refineSearch` - Search for jobs
- `jobDetails` - Get detailed job information
- Various configuration and metadata endpoints

### Authentication

The API uses:
1. **Session cookies** - `PLAY_SESSION`, `PHPPPE_ACT`, etc.
2. **CSRF tokens** - Passed via `x-csrf-token` header
3. **Company identifiers** - Each company has a unique code (e.g., `BECACA` for Bell Canada)

### Request Structure

A typical job search request:

```json
{
  "lang": "en_ca",
  "deviceType": "desktop",
  "country": "ca",
  "pageName": "search-results",
  "ddoKey": "refineSearch",
  "sortBy": "",
  "from": 0,
  "size": 10,
  "jobs": true,
  "counts": true,
  "keywords": "engineer",
  "siteType": "external",
  "selected_fields": {}
}
```

### Response Structure

```json
{
  "refineSearch": {
    "status": 200,
    "hits": 100,
    "totalHits": 427,
    "data": {
      "jobs": [
        {
          "jobId": "427845",
          "title": "Software Engineer",
          "location": "Toronto, Ontario",
          "category": "Technology",
          "description": "...",
          "city": "Toronto",
          "state": "Ontario",
          "country": "Canada",
          ...
        }
      ]
    },
    "facets": { ... }
  }
}
```

## Usage

### Basic Example

```python
from api_client import PhenomJobsClient

# Initialize client for Bell Canada
client = PhenomJobsClient(
    base_url="https://jobs.bell.ca",
    company_code="BECACA",
    locale="en_ca",
    country="ca"
)

# Search for jobs
results = client.search_jobs(keywords="software engineer", size=10)
jobs = client._extract_jobs(results)

for job in jobs:
    print(f"{job['title']} - {job['location']}")
```

### Get All Jobs from a Company

```python
# Fetch all available jobs (handles pagination automatically)
all_jobs = client.get_all_jobs(max_results=100)
print(f"Total jobs: {len(all_jobs)}")
```

### Search with Filters

```python
# Search with specific filters
results = client.search_jobs(
    keywords="engineer",
    category="Technology",
    from_index=0,
    size=20,
    sort_by="date",  # Sort by most recent
    filters={
        "state": ["Ontario"],
        "city": ["Toronto", "Montreal"],
        "experienceLevel": ["Mid-Career"]
    }
)
```

### Different Companies

```python
# GE Healthcare
ge_client = PhenomJobsClient(
    base_url="https://careers.gehealthcare.com",
    company_code="GEVGHLGLOBAL",
    locale="en_global",
    country="global"
)

jobs = ge_client.get_all_jobs(keywords="healthcare", max_results=50)
```

### Pagination

The API uses offset-based pagination:

```python
# First page (jobs 0-9)
page1 = client.search_jobs(from_index=0, size=10)

# Second page (jobs 10-19)
page2 = client.search_jobs(from_index=10, size=10)

# Third page (jobs 20-29)
page3 = client.search_jobs(from_index=20, size=10)
```

Or use `get_all_jobs()` to automatically handle pagination:

```python
all_jobs = client.get_all_jobs()  # Gets all jobs
```

## API Methods

### `__init__(base_url, company_code, locale, country)`

Initialize the client.

**Parameters:**
- `base_url` (str): Career site URL (e.g., "https://jobs.bell.ca")
- `company_code` (str): Company identifier (e.g., "BECACA")
- `locale` (str): Locale code (e.g., "en_ca", "en_global")
- `country` (str): Country code (e.g., "ca", "global")

### `search_jobs(keywords, location, category, from_index, size, sort_by, filters)`

Search for jobs.

**Parameters:**
- `keywords` (str): Search keywords
- `location` (str): Location filter
- `category` (str): Job category
- `from_index` (int): Starting index for pagination (default: 0)
- `size` (int): Results per page (default: 10, max: 100)
- `sort_by` (str): Sort order ("" for relevance, "date" for most recent)
- `filters` (dict): Additional filters

**Returns:** Dict with job results

### `get_all_jobs(keywords, location, category, max_results, filters)`

Get all jobs matching criteria with automatic pagination.

**Parameters:**
- `keywords` (str): Search keywords
- `location` (str): Location filter
- `category` (str): Job category
- `max_results` (int): Maximum results to return (None for all)
- `filters` (dict): Additional filters

**Returns:** List of job dictionaries

### `get_job_details(job_id)`

Get detailed information for a specific job.

**Parameters:**
- `job_id` (str): The job ID

**Returns:** Dict with detailed job information

## Company Codes Reference

To use this client with a new company, you need to find their:

1. **Base URL**: The career site URL (e.g., `https://careers.companyname.com`)
2. **Company Code**: Usually visible in API requests or page source (e.g., `COMPANYCODE`)
3. **Locale**: Language/region code (e.g., `en_us`, `en_global`, `fr_ca`)
4. **Country**: Country code (e.g., `us`, `ca`, `global`)

### How to Find Company Codes

1. Visit the company's career site
2. Open browser developer tools (F12)
3. Go to Network tab
4. Navigate to the job search page
5. Look for `/widgets` POST requests
6. Examine the request payload for the company code

### Known Company Codes

| Company | Base URL | Code | Locale | Country |
|---------|----------|------|--------|---------|
| Bell Canada | https://jobs.bell.ca | BECACA | en_ca | ca |
| GE Healthcare | https://careers.gehealthcare.com | GEVGHLGLOBAL | en_global | global |

## Limitations

1. **Rate Limiting**: The API may have rate limits. Be respectful with your requests.
2. **CSRF Tokens**: Tokens expire after some time. The client handles this by initializing a fresh session.
3. **Company-Specific Fields**: Different companies may have different job fields and categories.
4. **No Authentication**: This client only accesses public job listings. It doesn't handle job applications.

## Error Handling

The client returns error information in the response:

```python
result = client.search_jobs(keywords="test")

if "error" in result:
    print(f"Error: {result['error']}")
    print(f"Status code: {result.get('status_code')}")
else:
    # Process jobs
    jobs = client._extract_jobs(result)
```

## Advanced Usage

### Custom Session Configuration

```python
client = PhenomJobsClient(base_url="...", company_code="...")

# Add custom headers
client.session.headers.update({
    "User-Agent": "CustomBot/1.0"
})

# Add proxy
client.session.proxies = {
    "http": "http://proxy:8080",
    "https": "https://proxy:8080"
}
```

### Export to CSV

```python
import csv

jobs = client.get_all_jobs()

with open('jobs.csv', 'w', newline='', encoding='utf-8') as f:
    if jobs:
        writer = csv.DictWriter(f, fieldnames=jobs[0].keys())
        writer.writeheader()
        writer.writerows(jobs)
```

### Filter and Analyze

```python
jobs = client.get_all_jobs()

# Filter remote jobs
remote_jobs = [j for j in jobs if 'remote' in j.get('location', '').lower()]

# Group by category
from collections import Counter
categories = Counter(j.get('category', 'Unknown') for j in jobs)
print(categories)

# Filter by experience level
senior_jobs = [j for j in jobs if j.get('experienceLevel') == 'Senior Level']
```

## Running the Examples

```bash
python3 api_client.py
```

This will:
1. Search for engineering jobs at Bell Canada
2. Search for software jobs at GE Healthcare
3. Fetch all jobs and show category statistics

## Troubleshooting

### "Session initialized. CSRF token: Not found"

This warning is usually okay. The API might work without a CSRF token, or it will be obtained on the first request.

### Empty Results

- Check if the company code and locale are correct
- Try without filters first to verify the connection works
- Some companies may have different API structures

### Connection Errors

- Verify the base URL is correct
- Check your internet connection
- The site might be blocking automated requests (try adding a User-Agent header)

## License

This is a reverse-engineered API client for educational purposes. Use responsibly and in accordance with the terms of service of the websites you're accessing.

## Disclaimer

This client is not officially affiliated with Phenom People Inc. or any of the companies using their platform. Use at your own risk and ensure compliance with the websites' terms of service.
