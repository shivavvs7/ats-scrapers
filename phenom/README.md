# Phenom People ATS Scraper

Production-ready scraper for Phenom People-powered career sites.

## Overview

Phenom People is a leading talent experience management platform used by hundreds of companies worldwide. Unlike other ATS platforms, Phenom companies use **custom branded domains** with no standard URL pattern, making discovery more challenging.

**Examples:**
- Bell Canada: `https://jobs.bell.ca`
- GE Healthcare: `https://careers.gehealthcare.com`
- Each company has a unique domain

## Features

✅ **12-hour caching** - Prevents redundant scraping
✅ **Automatic pagination** - Retrieves all jobs using `PhenomJobsClient.get_all_jobs()`
✅ **Retry logic** - 3 attempts with exponential backoff
✅ **Async support** - Efficient batch scraping
✅ **Standardized CSV export** - Compatible with other ATS scrapers
✅ **Pydantic validation** - Type-safe job data
✅ **Detection tools** - Identify Phenom-powered sites
✅ **Config extraction** - Helper tools for adding new companies

## Quick Start

### 1. Scrape All Companies

```bash
python phenom/main.py
```

This scrapes all companies from `phenom/companies.csv` (respects 12-hour cache).

### 2. Scrape Single Company

```bash
python phenom/main.py https://jobs.bell.ca
```

Company must exist in `companies.csv` with proper configuration.

### 3. Force Re-scrape

```bash
python phenom/main.py --force
```

Ignores cache and re-scrapes all companies.

### 4. Export to CSV

```bash
python phenom/export_to_csv.py
```

Generates `phenom/jobs.csv` with standardized format:
- `url` - Job application URL
- `title` - Job title
- `location` - Job location
- `company` - Company name
- `ats_id` - Phenom job ID
- `id` - Generated UUID

## File Structure

```
phenom/
├── main.py                         # Main scraper
├── export_to_csv.py                # CSV export utility
├── detect_phenom.py                # Detection tool
├── extract_company_config.py       # Config extraction tool
├── companies.csv                   # Company configurations
├── jobs.csv                        # Exported jobs (generated)
├── companies/                      # Scraped JSON data
│   ├── jobs.bell.ca.json
│   └── careers.gehealthcare.com.json
└── phenom_jobs_api/               # API client library
    ├── api_client.py
    ├── README.md
    └── test_api.py
```

## Company Configuration

Each company requires 5 pieces of configuration in `companies.csv`:

| Field | Description | Example |
|-------|-------------|---------|
| `url` | Career site URL | `https://jobs.bell.ca` |
| `name` | Company name | `Bell Canada` |
| `company_code` | Phenom company identifier | `BECACA` |
| `locale` | Language/region code | `en_ca` |
| `country` | Country code | `ca` |

### Example CSV Entry

```csv
url,name,company_code,locale,country
https://jobs.bell.ca,Bell Canada,BECACA,en_ca,ca
https://careers.gehealthcare.com,GE Healthcare,GEVGHLGLOBAL,en_global,global
```

## Adding New Companies

### Step 1: Detect Phenom Platform

Use the detection tool to verify the site uses Phenom:

```bash
python phenom/detect_phenom.py https://careers.example.com -v
```

**Output:**
```
Phenom Detected: Yes
Confidence: high

Detected Signals (4):
  • Phenom cookies: PLAY_SESSION, PHPPPE_ACT
  • Phenom reference in HTML
  • Phenom JavaScript detected
  • /widgets endpoint exists
```

If detection fails, the site does not use Phenom.

### Step 2: Extract Configuration

#### Method A: Automatic Extraction (Limited)

```bash
python phenom/extract_company_config.py https://careers.example.com
```

This can extract `locale` and `country` but **rarely finds the company_code automatically**.

#### Method B: Manual Extraction (Recommended)

**Finding company_code, locale, and country:**

1. **Visit the career site** in your browser
2. **Open DevTools** (F12 or Cmd+Option+I)
3. **Go to Network tab**
4. **Search for any job** on the site
5. **Find POST request to `/widgets`**
   - Filter by "XHR" or "Fetch"
   - Look for URL ending in `/widgets`
6. **Click on the request → Payload tab**
7. **Extract from the payload:**
   ```json
   {
     "lang": "en_ca",           ← This is your locale
     "country": "ca",            ← This is your country
     "pageName": "search-results",
     ...
   }
   ```

8. **Find company_code:**
   - Check the request headers for custom fields
   - OR search the page source (View Page Source)
   - Look for patterns like: `companyCode: "BECACA"`
   - OR check cookies in DevTools → Application → Cookies
   - Company codes are usually ALL CAPS (e.g., `BECACA`, `GEVGHLGLOBAL`)

**Alternative: HAR File Method**

1. In DevTools → Network tab, **click the "Export HAR" button**
2. Save the HAR file
3. Run:
   ```bash
   python phenom/extract_company_config.py --har captured_traffic.har
   ```

### Step 3: Add to CSV

Once you have all configuration, add to `phenom/companies.csv`:

```csv
https://careers.example.com,Example Corp,EXAMPLECO,en_us,us
```

### Step 4: Test Scraping

```bash
python phenom/main.py https://careers.example.com
```

If successful, you'll see:
```
Successfully scraped X jobs from careers.example.com
```

## Known Companies

| Company | URL | Company Code | Locale | Country | Jobs |
|---------|-----|--------------|--------|---------|------|
| Bell Canada | jobs.bell.ca | BECACA | en_ca | ca | ~91 |
| GE Healthcare | careers.gehealthcare.com | GEVGHLGLOBAL | en_global | global | ~1,228 |

**More companies available:** [TheirStack Phenom List](https://theirstack.com/en/technology/phenom-people) (156+ companies)

## Discovery Strategy

### Challenge: No Standard URL Pattern

Phenom is unique among ATS platforms:
- ❌ No pattern like `lever.co/[company]`
- ❌ No pattern like `greenhouse.io/[company]`
- ❌ No pattern like `*.oraclecloud.com`
- ✅ Each company has a **custom branded domain**

This makes automated discovery difficult.

### Recommended Approaches

#### 1. TheirStack Company List (Best Starting Point)

**Source:** [TheirStack Phenom People](https://theirstack.com/en/technology/phenom-people)

**Available:**
- 156 companies total
- 62 in United States
- 4 in Canada
- Regional breakdowns

**Process:**
1. Manually visit TheirStack and compile list
2. For each company, use `detect_phenom.py` to verify
3. Use `extract_company_config.py` to get configuration
4. Add to `companies.csv`

#### 2. Known Customer Research

Phenom's known customers include:
- Gamestop
- Thomson Reuters
- Philips
- Truist Bank
- Citrix
- Walmart
- IBM
- Intel

Search for "[Company] careers" and use detection tools.

#### 3. Technical Fingerprinting

Use `detect_phenom.py` on suspected sites:

```bash
python phenom/detect_phenom.py https://careers.example.com
```

**Phenom signatures:**
- `PLAY_SESSION` and `PHPPPE_ACT` cookies
- `/widgets` POST endpoint
- Phenom JavaScript references
- "Powered by Phenom" footer

## API Details

### Phenom Jobs API

Phenom uses a unified API across all companies:

**Endpoint:** `POST {base_url}/widgets`

**Request Structure:**
```json
{
  "lang": "en_ca",
  "deviceType": "desktop",
  "country": "ca",
  "pageName": "search-results",
  "ddoKey": "refineSearch",
  "from": 0,
  "size": 100,
  "jobs": true,
  "keywords": "",
  "selected_fields": {}
}
```

**Response Structure:**
```json
{
  "refineSearch": {
    "totalHits": 427,
    "data": {
      "jobs": [
        {
          "jobId": "427845",
          "title": "Software Engineer",
          "location": "Toronto, Ontario",
          "city": "Toronto",
          "state": "Ontario",
          "country": "Canada",
          "category": "Technology",
          ...
        }
      ]
    }
  }
}
```

### PhenomJobsClient

The API client (`phenom_jobs_api/api_client.py`) handles:
- ✅ Session initialization with CSRF tokens
- ✅ Automatic pagination
- ✅ Search with filters
- ✅ Job details retrieval

See [phenom_jobs_api/README.md](phenom_jobs_api/README.md) for full API documentation.

## Data Format

### Stored JSON (companies/*.json)

```json
{
  "last_scraped": "2026-02-02T12:34:56.789",
  "name": "Bell Canada",
  "config": {
    "company_code": "BECACA",
    "locale": "en_ca",
    "country": "ca"
  },
  "jobs": [
    {
      "jobId": "427845",
      "title": "Software Engineer",
      "location": "Toronto, Ontario",
      "city": "Toronto",
      "state": "Ontario",
      "country": "Canada",
      "category": "Technology",
      "description": "...",
      ...
    }
  ]
}
```

### Exported CSV (jobs.csv)

```csv
url,title,location,company,ats_id,id
https://jobs.bell.ca/job/427845,Software Engineer,"Toronto, Ontario, Canada",Bell Canada,427845,1d34e107-7928-535e-9f95-3fe3f3ccb4ef
```

## Caching

### 12-Hour Cache

Jobs are cached for **12 hours** to prevent redundant scraping:

- ✅ First scrape: Downloads all jobs
- ⏭️ Within 12 hours: Skips scraping, uses cached data
- 🔄 After 12 hours: Re-scrapes automatically

**Override cache:**
```bash
python phenom/main.py --force
```

### Cache Location

Cached data is stored in `phenom/companies/{domain}.json`.

Example: `phenom/companies/jobs.bell.ca.json`

## Limitations

### 1. Company Code Extraction is Manual

Unlike other ATS platforms, Phenom company codes **cannot be easily automated**:
- Not in URLs
- Not consistently in page source
- Requires browser inspection

**Solution:** Use `extract_company_config.py` with manual DevTools inspection.

### 2. No Automated Discovery

Cannot add to `searxng_discovery.py` like other ATS platforms:
- No URL pattern to search for
- Each company has unique domain

**Solution:** Use TheirStack list + detection tools.

### 3. Job URL Construction

Job URLs are constructed as `{base_url}/job/{jobId}`.

This format may vary by company. If URLs don't work:
1. Visit the career site
2. Click on a job
3. Note the URL pattern
4. Update `construct_job_url()` in `export_to_csv.py`

### 4. Rate Limiting

The API may have rate limits. The scraper includes:
- Delays between requests
- Retry logic with exponential backoff
- Respectful request patterns

## Troubleshooting

### "Missing company_code" Error

```
Error: Missing company_code for jobs.bell.ca in CSV
```

**Solution:** Ensure `companies.csv` has the `company_code` column filled:
```csv
url,name,company_code,locale,country
https://jobs.bell.ca,Bell Canada,BECACA,en_ca,ca
```

### "Company not found in CSV"

```
Error: Company jobs.bell.ca not found in companies.csv
```

**Solution:** Add the company to `companies.csv` before scraping.

### No Jobs Found

```
No jobs found for careers.example.com
```

**Possible causes:**
1. **Wrong company_code** - Verify with DevTools
2. **Wrong locale/country** - Check the /widgets request payload
3. **Company has no open jobs** - Verify on their website
4. **API change** - Company may have customized their Phenom setup

### Session/CSRF Errors

```
Session initialized. CSRF token: Not found
```

This warning is usually **okay**. The API often works without CSRF tokens.

If scraping fails:
1. Try with a different locale/country
2. Check if the site is blocking automated requests
3. Add User-Agent header customization

## Integration with Pipeline

### Full Pipeline

```bash
# 1. Scrape all companies
python phenom/main.py

# 2. Export to CSV
python phenom/export_to_csv.py

# 3. Verify output
head phenom/jobs.csv
wc -l phenom/jobs.csv
```

### Add to Continuous Discovery

While Phenom cannot be added to `searxng_discovery.py`, you can:

1. **Monitor TheirStack** for new Phenom adoptions
2. **Periodically run detection** on known companies' career sites
3. **Add to batch scraping** in `full_pipeline.sh`

## Performance

### Benchmarks (February 2026)

| Company | Jobs | Scrape Time | Rate |
|---------|------|-------------|------|
| Bell Canada | 91 | 2.9s | 31 jobs/s |
| GE Healthcare | 1,228 | 10.2s | 120 jobs/s |

### Optimization

- ✅ Uses `page_size=100` for efficient pagination
- ✅ Async/await for concurrent operations
- ✅ Connection pooling with requests.Session
- ✅ 12-hour caching reduces API load

## References

### External Resources

- [Phenom People Official Site](https://www.phenom.com/)
- [TheirStack Phenom Companies (156)](https://theirstack.com/en/technology/phenom-people)

### Related Files

- API Client: `phenom/phenom_jobs_api/api_client.py`
- API Documentation: `phenom/phenom_jobs_api/README.md`
- Pydantic Model: `models/phenom.py`
- Export Utilities: `export_utils.py`

### Reference Implementations

- Lever: `lever/main.py`
- Oracle: `oracle/main.py`
- Greenhouse: `greenhouse/main.py`

## Contributing

### Adding New Companies

1. Use detection tool to verify Phenom
2. Extract configuration (company_code, locale, country)
3. Add to `companies.csv`
4. Test scraping
5. Submit pull request

### Reporting Issues

- Company scraping fails
- Wrong job URLs
- Missing configuration

## License

Part of the Stapply AI data pipeline. Use in accordance with website terms of service.
