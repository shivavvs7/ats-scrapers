# Gem ATS Job Scraper

A production-ready Python client for scraping job listings from Gem ATS (Applicant Tracking System). This scraper uses the public GraphQL API to fetch job postings for any company hosted on `jobs.gem.com`.

## Overview

Gem ATS is an applicant tracking system used by many companies to host their job boards. This scraper provides a simple, robust interface to programmatically access job listings without requiring authentication.

## Discovered APIs

### GraphQL Batch Endpoint

**Endpoint:** `https://jobs.gem.com/api/public/graphql/batch`

**Method:** POST

**Content-Type:** application/json

This endpoint accepts batched GraphQL queries, allowing multiple queries to be sent in a single request. The API returns job postings, company information, filters, and branding themes.

### Key GraphQL Queries

1. **JobBoardTheme** - Fetches branding theme information for a company's job board
2. **JobBoardList** - Fetches all job postings, filters, and company information

## Authentication

**No authentication required!** This is a public API that can be accessed without API keys, tokens, or credentials. Only standard HTTP headers are needed.

## Installation

### Requirements

- Python 3.7+
- `requests` library

### Setup

```bash
# Install required dependencies
pip install requests

# Make the script executable (optional)
chmod +x api_client.py
```

## Usage

### Basic Example

```python
from api_client import GemATSScraper

# Initialize the scraper
scraper = GemATSScraper()

# Fetch all jobs for a company
jobs = scraper.get_job_postings('accel')

for job in jobs:
    print(f"{job.title} - {job.job.employment_type}")
    for location in job.locations:
        print(f"  Location: {location.name}")

# Close the session
scraper.close()
```

### Using Context Manager (Recommended)

```python
from api_client import GemATSScraper

with GemATSScraper() as scraper:
    jobs = scraper.get_job_postings('alex-and-ani')
    print(f"Found {len(jobs)} jobs")
```

### Get Company Information

```python
with GemATSScraper() as scraper:
    company = scraper.get_company_info('accel')
    print(f"Company: {company.team_display_name}")
    print(f"Page Title: {company.page_title}")
```

### Group Jobs by Department

```python
with GemATSScraper() as scraper:
    jobs_by_dept = scraper.get_jobs_by_department('alex-and-ani')

    for dept_name, jobs in jobs_by_dept.items():
        print(f"\n{dept_name}:")
        for job in jobs:
            print(f"  - {job.title}")
```

### Group Jobs by Location

```python
with GemATSScraper() as scraper:
    jobs_by_location = scraper.get_jobs_by_location('accel')

    for location_name, jobs in jobs_by_location.items():
        print(f"\n{location_name}:")
        for job in jobs:
            print(f"  - {job.title}")
```

### Export to JSON

```python
with GemATSScraper() as scraper:
    # Export with default filename: accel_jobs.json
    filename = scraper.export_to_json('accel')
    print(f"Exported to {filename}")

    # Export with custom filename
    filename = scraper.export_to_json('alex-and-ani', 'custom_output.json')
    print(f"Exported to {filename}")
```

### Run the Example Script

```bash
python api_client.py
```

This will:
1. Fetch jobs from Accel
2. Fetch jobs from Alex and Ani (grouped by department)
3. Export both to JSON files

## API Reference

### GemATSScraper Class

#### Methods

##### `__init__(session: Optional[requests.Session] = None)`
Initialize the scraper with an optional session for connection pooling.

##### `get_jobs(company_id: str) -> Dict[str, Any]`
Fetch raw job data including postings, filters, company info, and theme.

**Parameters:**
- `company_id` (str): Company identifier from the URL (e.g., 'accel', 'alex-and-ani')

**Returns:**
- Dictionary containing:
  - `job_postings`: List of raw job posting data
  - `filters`: Available filters (departments, locations)
  - `company_info`: Company information
  - `theme`: Branding theme (if available)

##### `get_job_postings(company_id: str) -> List[JobPosting]`
Fetch and parse job postings into structured objects.

**Parameters:**
- `company_id` (str): Company identifier

**Returns:**
- List of `JobPosting` objects

##### `get_company_info(company_id: str) -> CompanyInfo`
Fetch company information.

**Parameters:**
- `company_id` (str): Company identifier

**Returns:**
- `CompanyInfo` object

##### `get_jobs_by_department(company_id: str) -> Dict[str, List[JobPosting]]`
Fetch jobs grouped by department.

**Parameters:**
- `company_id` (str): Company identifier

**Returns:**
- Dictionary mapping department names to lists of `JobPosting` objects

##### `get_jobs_by_location(company_id: str) -> Dict[str, List[JobPosting]]`
Fetch jobs grouped by location.

**Parameters:**
- `company_id` (str): Company identifier

**Returns:**
- Dictionary mapping location names to lists of `JobPosting` objects

##### `export_to_json(company_id: str, filename: Optional[str] = None) -> str`
Export job postings to a JSON file.

**Parameters:**
- `company_id` (str): Company identifier
- `filename` (str, optional): Output filename (default: `{company_id}_jobs.json`)

**Returns:**
- Path to the exported file

##### `close()`
Close the HTTP session.

### Data Classes

#### JobPosting
Represents a complete job posting.

**Attributes:**
- `id` (str): Internal job posting ID
- `ext_id` (str): External job posting ID
- `title` (str): Job title
- `locations` (List[Location]): List of job locations
- `job` (Job): Job details

#### Location
Represents a job location.

**Attributes:**
- `id` (str): Location ID
- `name` (str): Location name
- `city` (str): City name
- `iso_country` (str): ISO country code
- `is_remote` (bool): Whether the location is remote
- `ext_id` (str): External location ID

#### Job
Represents job details.

**Attributes:**
- `id` (str): Job ID
- `department` (Optional[Department]): Department information
- `location_type` (str): Location type (e.g., 'REMOTE', 'IN_OFFICE', 'HYBRID')
- `employment_type` (str): Employment type (e.g., 'FULL_TIME', 'INTERN', 'PART_TIME')

#### Department
Represents a job department.

**Attributes:**
- `id` (str): Department ID
- `name` (str): Department name
- `ext_id` (str): External department ID

#### CompanyInfo
Represents company information.

**Attributes:**
- `id` (str): Company ID
- `team_display_name` (str): Company display name
- `description_html` (Optional[str]): Company description (HTML)
- `page_title` (str): Page title

## Finding Company IDs

To find the company ID for any Gem ATS job board:

1. Navigate to the company's job board URL (e.g., `https://jobs.gem.com/accel`)
2. The company ID is the last part of the URL path (e.g., `accel`)

Examples:
- `https://jobs.gem.com/accel` → company_id: `accel`
- `https://jobs.gem.com/alex-and-ani` → company_id: `alex-and-ani`
- `https://jobs.gem.com/your-company` → company_id: `your-company`

## Response Data Structure

### Example Job Posting Response

```json
{
  "id": "T2F0c0pvYlBvc3Q6MTQ3MTgxMA==",
  "extId": "am9icG9zdDqEV9vb3qjLH8DFZNwUZlN5",
  "title": "Accel Summer Intern 2026",
  "locations": [
    {
      "id": "14895",
      "name": "San Francisco",
      "city": "San Francisco",
      "isoCountry": "USA",
      "isRemote": false,
      "extId": "bG9jOjPQf5aWeu33nxiFZUzEoHc"
    }
  ],
  "job": {
    "id": "T2F0c0pvYjo4Njc2NDk=",
    "department": null,
    "locationType": "IN_OFFICE",
    "employmentType": "INTERN"
  }
}
```

## Error Handling

The scraper includes comprehensive error handling:

```python
from api_client import GemATSScraper
import requests

with GemATSScraper() as scraper:
    try:
        jobs = scraper.get_job_postings('company-id')
    except requests.RequestException as e:
        print(f"Network error: {e}")
    except ValueError as e:
        print(f"Data parsing error: {e}")
```

## Limitations

1. **Public Data Only**: Only public job postings are accessible. Internal or draft postings are not available.

2. **Rate Limiting**: While no explicit rate limits were observed during testing, it's recommended to implement respectful scraping practices:
   - Add delays between requests if scraping multiple companies
   - Use the same session for multiple requests (connection pooling)
   - Cache results when possible

3. **No Job Details**: The API only returns job listing metadata. Full job descriptions may require visiting individual job pages.

4. **Company-Specific Availability**: This scraper only works for companies using Gem ATS and hosting their job boards on `jobs.gem.com`.

## Best Practices

1. **Use Context Manager**: Always use the context manager pattern to ensure sessions are properly closed:
   ```python
   with GemATSScraper() as scraper:
       # Your code here
   ```

2. **Reuse Sessions**: For multiple requests, reuse the same scraper instance:
   ```python
   with GemATSScraper() as scraper:
       jobs1 = scraper.get_job_postings('company1')
       jobs2 = scraper.get_job_postings('company2')
   ```

3. **Error Handling**: Always wrap API calls in try-except blocks for production use.

4. **Caching**: Consider caching results to reduce API calls:
   ```python
   import json

   # Cache results
   filename = scraper.export_to_json('accel')

   # Load from cache later
   with open(filename) as f:
       cached_data = json.load(f)
   ```

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

## License

MIT License - Feel free to use this code in your projects.

## Disclaimer

This scraper is for educational and research purposes. Please review and comply with Gem's Terms of Service when using this tool. Always respect rate limits and scrape responsibly.

## Support

For issues, questions, or contributions, please visit the project repository.

---

**Last Updated:** February 1, 2026

**API Version:** Public GraphQL API (v2)
