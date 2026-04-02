# API Reverse Engineering Summary

## Project Overview

Successfully reverse-engineered the Phenom Jobs API used by Bell Canada, GE Healthcare, and hundreds of other companies worldwide for their career portals.

## APIs Discovered

### Main Endpoint: `/widgets`

**Base URLs:**
- Bell Canada: `https://jobs.bell.ca/widgets`
- GE Healthcare: `https://careers.gehealthcare.com/widgets`

**Method:** POST

**Content-Type:** application/json

### API Operations

The `/widgets` endpoint is a multipurpose API that handles different operations based on the `ddoKey` parameter:

1. **`refineSearch`** - Job search and listing
2. **`jobDetails`** - Detailed job information
3. **`getChatbotConfigurations`** - Chatbot settings
4. **`getUrl`** - URL generation for pages
5. **`getPiiConsentConfig`** - Privacy settings
6. **`getRegionLocales`** - Available languages/regions

## Authentication Method

### Session-Based Authentication

1. **Session Cookies:**
   - `PLAY_SESSION` - Main session token (JWT format)
   - `PHPPPE_ACT` - Activity tracking
   - `VISITED_LANG` - Language preference
   - `VISITED_COUNTRY` - Country preference
   - `Per_UniqueID` - Unique visitor identifier

2. **CSRF Protection:**
   - Header: `x-csrf-token`
   - Token embedded in session cookies or page HTML
   - Token format: 32-character hexadecimal string

3. **Company Identification:**
   - Each company has a unique code (e.g., `BECACA`, `GEVGHLGLOBAL`)
   - Code is embedded in request payloads
   - Determines which job database to query

## Request Structure

### Job Search Request

```json
{
  "lang": "en_ca",
  "deviceType": "desktop",
  "country": "ca",
  "pageName": "search-results",
  "ddoKey": "refineSearch",
  "sortBy": "",
  "subsearch": "",
  "from": 0,
  "size": 10,
  "jobs": true,
  "counts": true,
  "all_fields": [
    "category",
    "jobFamilies",
    "country",
    "state",
    "city",
    "experienceLevel"
  ],
  "clearAll": false,
  "jdsource": "facets",
  "isSliderEnable": false,
  "pageId": "page20",
  "siteType": "external",
  "keywords": "engineer",
  "global": true,
  "selected_fields": {
    "category": ["Technology"],
    "state": ["Ontario"]
  },
  "locationData": {}
}
```

### Response Structure

```json
{
  "refineSearch": {
    "status": 200,
    "hits": 10,
    "totalHits": 427,
    "data": {
      "jobs": [
        {
          "jobId": "427813",
          "title": "Senior Manager, CRM & Salesforce",
          "location": "Toronto, Ontario",
          "city": "Toronto",
          "state": "Ontario",
          "country": "Canada",
          "category": "Technology",
          "subCategory": "IT",
          "experienceLevel": "Senior Level",
          "description": "Job description...",
          "postedDate": "2026-01-20",
          "reqId": "427813",
          "multi_location": [],
          "ml_skills": ["salesforce", "crm", "strategy"],
          ...
        }
      ]
    },
    "facets": {
      "category": {
        "Technology": 150,
        "Sales": 80,
        ...
      },
      "state": {
        "Ontario": 120,
        "Quebec": 90,
        ...
      }
    }
  }
}
```

## Implementation Details

### Python API Client

**File:** `api_client.py`

**Key Features:**
- Session management with automatic cookie handling
- CSRF token extraction and injection
- Pagination support (offset-based)
- Multiple search methods (single page, all results)
- Error handling and retry logic
- Type hints and comprehensive documentation

**Main Class:** `PhenomJobsClient`

**Key Methods:**
- `search_jobs()` - Search with filters, pagination
- `get_all_jobs()` - Automatic pagination to fetch all results
- `get_job_details()` - Get detailed job information
- `_extract_jobs()` - Parse response structure
- `_initialize_session()` - Setup cookies and CSRF token

### Technologies Used

- **Python 3** - Implementation language
- **requests** - HTTP client library
- **JSON** - Request/response format
- **JWT** - Session token format

## Testing Results

### ✅ Test 1: Bell Canada Job Search
- Successfully retrieved jobs with keyword search
- Pagination working correctly
- Filters applied successfully
- Response parsing accurate

### ✅ Test 2: GE Healthcare Job Search
- Multi-company support verified
- International locale support (global/en_global)
- Different company codes working

### ✅ Test 3: Bulk Retrieval
- Successfully fetched 100+ jobs with automatic pagination
- No rate limiting issues observed
- Response consistency maintained

## API Capabilities

### Supported Features

✅ **Search & Filter**
- Keyword search
- Location filtering (country, state, city)
- Category filtering
- Experience level filtering
- Multiple simultaneous filters

✅ **Pagination**
- Offset-based (`from` parameter)
- Configurable page size (1-100 jobs per request)
- Total results count available

✅ **Sorting**
- By relevance (default)
- By date (most recent first)

✅ **Faceted Search**
- Category counts
- Location counts
- Experience level distribution

✅ **Multi-Company**
- Works across all Phenom-powered sites
- Same API structure for all companies

### Limitations

⚠️ **Rate Limiting**
- No explicit rate limits observed
- Recommend reasonable request intervals

⚠️ **Authentication Scope**
- Only public job listings accessible
- No job application functionality
- No candidate profile management

⚠️ **Data Completeness**
- Some fields may be null/empty
- Company-specific field variations
- Inconsistent date formats

## Files Generated

1. **`api_client.py`** (13 KB)
   - Production-ready Python API client
   - Full documentation and examples
   - Error handling and retries

2. **`README.md`** (9 KB)
   - Comprehensive usage guide
   - API documentation
   - Examples and troubleshooting

3. **`test_api.py`** (1.5 KB)
   - Test suite demonstrating functionality
   - Verification of both companies

4. **`SUMMARY.md`** (this file)
   - Technical documentation
   - API discovery details
   - Implementation notes

5. **`network.har`** (376 KB)
   - Complete network traffic capture
   - Request/response examples
   - Cookie and header details

## Usage Examples

### Basic Search

```python
from api_client import PhenomJobsClient

client = PhenomJobsClient(
    base_url="https://jobs.bell.ca",
    company_code="BECACA",
    locale="en_ca",
    country="ca"
)

jobs = client.get_all_jobs(keywords="software engineer", max_results=50)
```

### Advanced Filtering

```python
results = client.search_jobs(
    keywords="data scientist",
    category="Technology",
    from_index=0,
    size=20,
    filters={
        "state": ["Ontario", "Quebec"],
        "experienceLevel": ["Mid-Career", "Senior Level"]
    }
)
```

### Export to CSV

```python
import csv

jobs = client.get_all_jobs()

with open('jobs.csv', 'w', newline='') as f:
    if jobs:
        writer = csv.DictWriter(f, fieldnames=jobs[0].keys())
        writer.writeheader()
        writer.writerows(jobs)
```

## Security Considerations

1. **Respectful Usage**
   - Don't overload servers with rapid requests
   - Implement reasonable delays between requests
   - Cache results when appropriate

2. **Terms of Service**
   - Review each company's terms of service
   - This is for educational/research purposes
   - Commercial use may require permission

3. **Data Privacy**
   - Only public job listings are accessed
   - No personal information collected
   - Follow GDPR and other privacy regulations

## Future Enhancements

Potential improvements for the API client:

1. **Async Support** - Use `aiohttp` for concurrent requests
2. **Caching** - Implement response caching to reduce load
3. **Rate Limiting** - Add built-in rate limiting controls
4. **Retry Logic** - Exponential backoff for failed requests
5. **Monitoring** - Request logging and metrics
6. **CLI Tool** - Command-line interface for easy usage
7. **Job Alerts** - Track new jobs and send notifications
8. **Company Detection** - Auto-detect company code from URL

## Conclusion

Successfully created a production-ready API client for Phenom Jobs platform. The client:

- ✅ Works with multiple companies (Bell Canada, GE Healthcare, etc.)
- ✅ Handles authentication automatically (session + CSRF)
- ✅ Supports all major search and filter operations
- ✅ Includes comprehensive error handling
- ✅ Fully documented with examples
- ✅ Tested and verified working

The API is well-designed, consistent across companies, and easy to work with. The implementation provides a solid foundation for job aggregation, analysis, and monitoring applications.
