# Oracle HCM Cloud (Oracle Recruiting Cloud) Integration

Complete discovery and scraping implementation for Oracle HCM Cloud ATS platform.

## Overview

Oracle HCM Cloud (formerly Oracle Recruiting Cloud) is an enterprise recruiting platform used by large companies like Oracle, City of Atlanta, TTX, EXP, CooperCompanies, Kroll, and many others.

**URL Pattern:** `https://{subdomain}.fa.{region}.oraclecloud.com`
**Example:** `https://eeho.fa.us2.oraclecloud.com` (Oracle's careers site)

## Features

- ✅ **Discovery:** Automatically find Oracle HCM Cloud companies using SearXNG
- ✅ **Name Enrichment:** Scrape actual company names from careers pages
- ✅ **Job Scraping:** Fetch all jobs via Oracle Recruiting API
- ✅ **Pagination:** Handle large job datasets (100 jobs per page)
- ✅ **Caching:** 12-hour cache to avoid redundant scraping
- ✅ **CSV Export:** Standardized job export with generated IDs
- ✅ **URL Construction:** Build job URLs when API doesn't provide them

## Directory Structure

```
oracle/
├── main.py                     # Main scraper
├── export_to_csv.py           # CSV export utility
├── enrich_company_names.py    # Company name enrichment utility
├── oracle_companies.csv       # Discovered companies
├── companies/                 # Scraped job data (JSON)
│   ├── eeho-us2.json         # Oracle (4,390 jobs)
│   ├── ejjc-us6.json         # TTX
│   └── ...
├── jobs.csv                   # Exported jobs (CSV)
└── scripts/
    └── oracle_ats_client/     # Production-ready API client
        ├── api_client.py
        ├── README.md
        └── SUMMARY.md
```

## Usage

### 1. Discovery

Discover Oracle HCM Cloud companies:

```bash
# Discover using local SearXNG instance
python searxng_discovery.py --platform oracle --local-only

# Discover using cloud instances (more results)
python searxng_discovery.py --platform oracle --use-cloud --max-queries 50

# Quick test (5 queries, 2 pages each)
python searxng_discovery.py --platform oracle --max-queries 5 --pages 2
```

**Output:** `oracle/oracle_companies.csv` with discovered companies

**Auto-Enrichment:** Company names are automatically enriched during discovery by scraping the actual company names from their careers pages.

### 2. Enrich Company Names

Manually enrich company names (if needed):

```bash
# Enrich all companies with generic names
python oracle/enrich_company_names.py

# Custom CSV path and delay
python oracle/enrich_company_names.py --csv oracle/oracle_companies.csv --delay 2.0
```

**What it does:**
- Fetches the careers page for each company
- Extracts the real company name from HTML metadata
- Updates `oracle_companies.csv` with actual names
- Skips companies that already have good names

**Example:**
- Before: `Ehxr, https://ehxr.fa.us2.oraclecloud.com`
- After: `City Of Atlanta, https://ehxr.fa.us2.oraclecloud.com`

### 3. Scrape Jobs

Scrape jobs from discovered companies:

```bash
# Scrape all companies
python oracle/main.py

# Force re-scrape (ignore 12-hour cache)
python oracle/main.py --force

# Scrape single company
python oracle/main.py https://eeho.fa.us2.oraclecloud.com

# Custom site number (if company uses non-default)
python oracle/main.py --site-number CX_45002 https://example.fa.us2.oraclecloud.com
```

**Output:** JSON files in `oracle/companies/` directory
**Example:** `oracle/companies/eeho-us2.json` (4,390 jobs)

**Features:**
- ✅ 12-hour caching (skips if scraped recently)
- ✅ Pagination (100 jobs per page, max 10,000 per company)
- ✅ Retry logic (3 attempts with exponential backoff)
- ✅ Metadata saved (subdomain, region, site_number)

### 4. Export to CSV

Export all jobs to standardized CSV format:

```bash
python oracle/export_to_csv.py
```

**Output:** `oracle/jobs.csv` with columns:
- `url` - Job application URL (constructed if not in API)
- `title` - Job title
- `location` - Location(s)
- `company` - Company name
- `ats_id` - Oracle requisition ID
- `id` - Generated UUID

**Example:**
```csv
url,title,location,company,ats_id,id
https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_45001/job/324695,Client Solution Executive,"ZURICH, Switzerland",Oracle,324695,01b0f894-d3a8-5816-b5af-814ad56ddd59
```

## Configuration

### Site Number

Oracle HCM Cloud uses a "site number" to identify the careers site. Default: `CX_45001`

Most companies use the default, but some have custom site numbers:

```bash
# Override site number
python oracle/main.py --site-number CX_45002 https://company.fa.us2.oraclecloud.com
```

**Future Enhancement:** Store site numbers in `oracle_companies.csv` for per-company config.

### Slug Format

File storage uses slug format: `{subdomain}-{region}`

**Examples:**
- `https://eeho.fa.us2.oraclecloud.com` → `eeho-us2.json`
- `https://amazon.fa.us1.oraclecloud.com` → `amazon-us1.json`
- `https://cvshealth.fa.us2.oraclecloud.com` → `cvshealth-us2.json`

## API Details

### Oracle Recruiting API Client

Located at: `oracle/scripts/oracle_ats_client/api_client.py`

**Key Methods:**
- `search_jobs(limit, offset, sort_by)` - Search/paginate jobs
- `get_job_details(job_id)` - Get detailed job info
- `extract_jobs_from_response()` - Helper to extract job list

**Job Fields:**
- Identifiers: `Id`, `JobId`, `RequisitionNumber`
- Details: `Title`, `ShortDescriptionStr`, `ExternalDescriptionInt`
- Location: `PrimaryLocation`, `Country`, `WorkLocation`, `otherWorkLocations`
- Dates: `PostedDate`, `ClosingDate`
- Categorization: `OrganizationName`, `JobCategoryName`, `JobFamilyName`
- Employment: `FullOrPartTime`, `FlexibleJobOption` (Remote/Hybrid/Onsite)
- URLs: `JobURL`, `ExternalApplyURL` (often null - we construct them)

### URL Construction

Since Oracle's API often doesn't return job URLs, we construct them:

**Pattern:**
```
https://{subdomain}.fa.{region}.oraclecloud.com/hcmUI/CandidateExperience/en/sites/{site_number}/job/{job_id}
```

**Example:**
```
https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_45001/job/324695
```

## Testing

### Test Discovery
```bash
python searxng_discovery.py --platform oracle --max-queries 2 --pages 2 --local-only
```

**Expected:**
- Discovers Oracle HCM Cloud URLs matching pattern
- Automatically enriches company names
- Saves to `oracle/oracle_companies.csv`

### Test Single Company Scrape
```bash
python oracle/main.py https://eeho.fa.us2.oraclecloud.com
```

**Expected:**
- Scrapes jobs from Oracle careers
- Saves to `oracle/companies/eeho-us2.json`
- Shows job count and pagination progress

### Test Caching
```bash
python oracle/main.py https://eeho.fa.us2.oraclecloud.com
```

**Expected:**
- Output: "Scraped eeho-us2 X hours ago. I will not scrape again."
- Skips scraping (unless >12 hours or `--force`)

### Test CSV Export
```bash
python oracle/export_to_csv.py
```

**Expected:**
- Reads all JSON files from `oracle/companies/`
- Validates with Pydantic models
- Exports to `oracle/jobs.csv`
- Shows job count

## Known Companies Using Oracle HCM Cloud

Seed data includes:
- **Oracle** - https://eeho.fa.us2.oraclecloud.com (4,390 jobs)
- **City of Atlanta** - https://ehxr.fa.us2.oraclecloud.com
- **TTX** - https://ejjc.fa.us6.oraclecloud.com
- **EXP** - https://elcn.fa.us2.oraclecloud.com
- **CooperCompanies** - https://hcjy.fa.us2.oraclecloud.com
- **Kroll** - https://hcxs.fa.us2.oraclecloud.com

Additional known companies (URLs to be verified):
- Amazon, CVS Health, IBM, Target, UPS, Walmart
- Accenture, Deloitte, EY, PwC
- Salesforce, Adobe, Cisco, Intel, Nike, Starbucks

## Integration with Continuous Discovery

Oracle is automatically included when running:

```bash
python run_discovery.py
```

The platform rotates through all ATS platforms including Oracle, discovering new companies continuously.

## Troubleshooting

### "Site number not found" error

Some companies use custom site numbers. Try:
1. Check the company's careers page HTML for site number
2. Use browser DevTools to inspect network requests
3. Try common alternatives: `CX_45001`, `CX_45002`, `CX_1`

### "Candidate Experience site" as company name

This is Oracle's default branding when companies haven't customized their careers page. The enrichment script filters this out and falls back to the subdomain-based name.

### No jobs returned

Possible causes:
- Wrong site number
- Company hasn't posted jobs yet
- Careers site requires authentication
- Subdomain is for internal use only

## Future Enhancements

1. **Site Number Detection:** Auto-detect site numbers from career page network requests
2. **Multi-Region Support:** Handle companies with multiple regional instances
3. **Company Metadata:** Store site_number in CSV for per-company configuration
4. **Rate Limiting:** Detect and respect Oracle API rate limits
5. **Legacy Taleo:** Separate implementation for legacy taleo.net platform

## References

- Oracle API Client: `oracle/scripts/oracle_ats_client/api_client.py`
- API Documentation: `oracle/scripts/oracle_ats_client/README.md`
- Implementation Summary: `oracle/scripts/oracle_ats_client/SUMMARY.md`
- Reference Scrapers: `lever/main.py`, `greenhouse/main.py`, `workable/main.py`
