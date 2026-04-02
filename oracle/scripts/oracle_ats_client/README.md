# Oracle Recruiting Cloud API Client

A production-ready Python client for interacting with Oracle's Recruiting Cloud (Oracle HCM CandidateExperience) API.

## Overview

This client provides a programmatic interface to Oracle's Applicant Tracking System (ATS) used by Oracle and other enterprises running Oracle HCM Cloud. It allows you to search for jobs, retrieve job details, get autocomplete suggestions, and search for recruiting events.

## Discovered APIs

Through reverse engineering Oracle's careers portal, the following API endpoints were identified:

### 1. Job Search API
- **Endpoint**: `/hcmRestApi/resources/latest/recruitingCEJobRequisitions`
- **Method**: GET
- **Purpose**: Search and filter job requisitions
- **Parameters**:
  - `keyword`: Search term for job titles, descriptions
  - `limit`: Number of results per page
  - `offset`: Pagination offset
  - `sortBy`: Sort order (POSTING_DATES_DESC, POSTING_DATES_ASC, RELEVANCY)
  - `facetsList`: Filters (LOCATIONS, TITLES, CATEGORIES, etc.)
  - `siteNumber`: Company-specific site identifier

### 2. Job Details API
- **Endpoint**: `/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails`
- **Method**: GET
- **Purpose**: Get comprehensive details about a specific job
- **Parameters**:
  - `Id`: Job requisition ID
  - `siteNumber`: Company-specific site identifier
  - `expand`: Set to "all" for full details

### 3. Apply Flow API
- **Endpoint**: `/hcmRestApi/resources/latest/recruitingCEApplyFlows`
- **Method**: GET
- **Purpose**: Get application flow configuration for a job
- **Parameters**:
  - `RequisitionNumber`: Job requisition number

### 4. Autocomplete APIs
- **Keyword Autocomplete**: `/hcmRestApi/resources/latest/recruitingCESearchAutoSuggestions?finder=findByKey`
- **Location Autocomplete**: `/hcmRestApi/resources/latest/recruitingCESearchAutoSuggestions?finder=findByLoc`
- **Purpose**: Provide search suggestions as users type

### 5. Events API
- **Endpoint**: `/hcmRestApi/resources/latest/recruitingCEEvents`
- **Method**: GET
- **Purpose**: Search for recruiting events (career fairs, info sessions, etc.)

### 6. Configuration APIs
- **Global Settings**: `/hcmRestApi/CandidateExperience/globalSettings`
- **Translations**: `/hcmRestApi/CandidateExperience/translations`

## Authentication

**No authentication required!** The Oracle Recruiting Cloud API is publicly accessible for job search and viewing. This is intentional to allow candidates to browse jobs without creating an account.

## Installation

### Requirements
- Python 3.7+
- `requests` library

### Setup
```bash
# Install dependencies
pip install requests

# Run the client
python api_client.py
```

## Usage

### Basic Example

```python
from api_client import OracleRecruitingClient

# Initialize client with Oracle's careers site
client = OracleRecruitingClient(
    base_url="https://eeho.fa.us2.oraclecloud.com",
    site_number="CX_45001"
)

# Search for jobs
results = client.search_jobs(keyword="software engineer", limit=10)

# Get job details
job_details = client.get_job_details(job_id="320918")

# Autocomplete suggestions
locations = client.autocomplete_locations("San Francisco")
```

### Advanced Usage

#### Pagination

```python
# Get page 2 of results (results 15-28)
results = client.search_jobs(
    keyword="data scientist",
    limit=14,
    offset=14,  # Skip first 14 results
    sort_by="RELEVANCY"
)
```

#### Sorting Options

```python
# Sort by posting date (newest first)
results = client.search_jobs(sort_by="POSTING_DATES_DESC")

# Sort by posting date (oldest first)
results = client.search_jobs(sort_by="POSTING_DATES_ASC")

# Sort by relevancy (requires keyword)
results = client.search_jobs(keyword="cloud", sort_by="RELEVANCY")
```

#### Custom Facets

```python
# Only get location facets
results = client.search_jobs(
    keyword="engineer",
    facets=["LOCATIONS", "WORK_LOCATIONS"]
)
```

#### Search Events

```python
# Find upcoming recruiting events
events = client.search_events(limit=10)

# Search events by keyword
events = client.search_events(keyword="career fair")
```

## Generalizing to Other Companies

This client is designed to work with any company using Oracle HCM Cloud Recruiting. To adapt it:

### Find the Base URL

Oracle HCM Cloud URLs follow this pattern:
```
https://{subdomain}.fa.{region}.oraclecloud.com
```

Examples:
- Oracle: `https://eeho.fa.us2.oraclecloud.com`
- Other companies will have different subdomains

### Find the Site Number

The site number is company-specific. You can find it by:

1. Visit the company's careers page
2. Open browser DevTools → Network tab
3. Search for a job
4. Look for API calls to `/hcmRestApi/resources/latest/recruitingCEJobRequisitions`
5. Find the `siteNumber` parameter in the URL (e.g., `siteNumber=CX_45001`)

### Example: Adapting for Another Company

```python
# Example for a hypothetical company using Oracle HCM
client = OracleRecruitingClient(
    base_url="https://example.fa.us2.oraclecloud.com",
    site_number="CX_12345"  # Company-specific site number
)

# Use the same methods
results = client.search_jobs(keyword="engineer")
```

## Response Format

### Job Search Response

```json
{
  "items": [
    {
      "Id": "320918",
      "Title": "Senior Program Manager",
      "PrimaryLocation": "United States",
      "PostedDate": "2026-01-25T01:54:00Z",
      "JobCategory": "Product Development",
      "WorkLocation": {...},
      "ExternalDescriptionInt": "Job description...",
      ...
    }
  ],
  "count": 4430,
  "hasMore": true,
  "limit": 14,
  "offset": 0
}
```

### Job Details Response

```json
{
  "items": [
    {
      "Id": "320918",
      "Title": "Senior Program Manager, Project Controls (Cost)",
      "PostedDate": "2026-01-25T01:54:00Z",
      "JobCategory": "Product Development",
      "ExternalDescriptionInt": "Full job description...",
      "Qualifications": "Requirements...",
      "PrimaryWorkLocation": "United States",
      "SecondaryWorkLocations": [],
      ...
    }
  ]
}
```

## Known Companies Using Oracle HCM Recruiting Cloud

Based on research, the following companies use Oracle HCM Cloud for recruiting:

- **Oracle** (obviously)
- **Amazon** - Various divisions
- **CVS Health**
- **Huawei**
- **Cargill**
- **McKesson**
- **IBM** - Some divisions
- **UnitedHealth Group**
- **Costco Wholesale**
- **Target**
- **UPS**

*Note: Many companies are migrating from legacy Taleo to Oracle Recruiting Cloud or other modern ATS systems.*

## Limitations

1. **Read-Only Access**: This client only supports reading job data. Applying for jobs requires user authentication and interaction with the web application.

2. **No Application Submission**: The API doesn't allow programmatic job applications. Users must apply through the web interface.

3. **Rate Limiting**: While not explicitly documented, excessive requests may be rate-limited. Implement appropriate delays in production.

4. **Site Number Required**: Each company has a unique site number that must be discovered manually.

5. **No User Profile APIs**: Candidate profile management, saved jobs, and application tracking require authentication.

## Error Handling

The client includes basic error handling:

```python
try:
    results = client.search_jobs(keyword="engineer")
except requests.exceptions.RequestException as e:
    print(f"Network error: {e}")
except ValueError as e:
    print(f"Invalid response: {e}")
```

## Testing

Run the example script to verify the client works:

```bash
python api_client.py
```

This will:
1. Search for "software engineer" jobs
2. Get details for a specific job
3. Test location autocomplete
4. Search for recruiting events

## Best Practices

1. **Respect Rate Limits**: Add delays between requests in production
2. **Cache Results**: Job listings don't change frequently, consider caching
3. **Error Handling**: Always wrap API calls in try-except blocks
4. **Timeouts**: Use appropriate timeouts to avoid hanging requests
5. **User-Agent**: Use a descriptive User-Agent header identifying your application

## Contributing

This client was reverse-engineered from Oracle's public careers portal. If you find additional endpoints or improvements:

1. Document the API endpoint
2. Add type hints and docstrings
3. Include example usage
4. Test with multiple Oracle HCM instances

## Legal & Ethical Considerations

- This client uses **publicly accessible** APIs that require no authentication
- All data accessed is intended for public viewing (job postings)
- Do not use this for:
  - Scraping large amounts of data
  - Circumventing application processes
  - Any purpose that violates Oracle's Terms of Service
- Use responsibly and ethically

## License

This code is provided as-is for educational and legitimate job search purposes.

## Support

For issues or questions:
1. Check that your base URL and site number are correct
2. Verify the company uses Oracle HCM Cloud (not Taleo Classic or other ATS)
3. Test the API endpoints directly in a browser or with curl
4. Check the browser Network tab for the exact API format used

---

**Generated by Claude Code** | 2026-01-25
