# Tesla Jobs Scraper

Automated scraper for Tesla careers that fetches all job listings with descriptions and outputs to `tesla.json`.

## Quick Start

```bash
python main.py
```

That's it! The script will:
1. ✅ Fetch all Tesla job listings
2. ✅ Load cached descriptions (if available)
3. ✅ Fetch only new job descriptions
4. ✅ Output to `tesla.json` at the root folder

## Output Format

The output file `tesla.json` follows this structure:

```json
{
  "last_scraped": "2026-01-17T20:30:20.628292",
  "name": "Tesla",
  "jobs": [
    {
      "url": "https://www.tesla.com/careers/search/job/...",
      "title": "AI Engineer, Manipulation, Optimus",
      "location": "Palo Alto, California",
      "description": "Full job description with responsibilities, requirements, and benefits...",
      "id": "224501",
      "department": "Tesla AI",
      "time_type": "Full-time"
    }
  ]
}
```

### Fields

- **last_scraped**: ISO datetime when the data was scraped
- **name**: Company name ("Tesla")
- **jobs**: Array of job objects

Each job contains:
- **url**: Direct link to Tesla job posting
- **title**: Job title
- **location**: Job location (city, state/country)
- **description**: Full HTML description including:
  - Job description
  - Responsibilities
  - Requirements
  - Compensation & Benefits
- **id**: Tesla job ID
- **department**: Department name (e.g., "Tesla AI")
- **time_type**: "Full-time", "Part-time", etc.

## Performance

### First Run (No Cache)
```
⏱️  ~1.5 hours
📦 Fetches all 4,807+ job descriptions
💾 Creates cache for future runs
```

### Subsequent Runs (With Cache)
```
⚡ ~5-30 seconds
📦 Only fetches new jobs (if any)
💾 Updates cache automatically
```

### Example Output
```
======================================================================
FETCH STATISTICS
======================================================================
✓ Loaded from cache: 4805
✓ Newly fetched: 2
✓ Total jobs processed: 4807
✓ Cache now contains: 4807 job descriptions
```

## Files Structure

```
tesla/
├── main.py                           # ← Run this file
├── tesla.json                        # ← Output file (24 MB)
├── cache/
│   ├── job_descriptions_cache.json   # Description cache (23 MB)
│   └── tesla.json                    # Raw API data (1.6 MB)
└── README.md                         # This file
```

## How It Works

1. **Browser Launch**: Automatically launches Chrome with debugging enabled
2. **Bot Detection**: Handles Akamai bot detection by loading Tesla careers page
3. **API Access**: Uses authenticated browser session to access Tesla's internal API
4. **Smart Caching**:
   - Checks cache for existing job descriptions
   - Only fetches missing/new jobs
   - Saves cache every 50 jobs (prevents data loss)
5. **Output**: Creates `tesla.json` in standard format

## Caching System

The scraper uses intelligent caching to dramatically speed up subsequent runs:

- **Cache File**: `cache/job_descriptions_cache.json`
- **Cache Size**: ~23 MB (4,807 jobs)
- **Update Strategy**: Automatic - fetches only new/missing jobs
- **Persistence**: Cache survives across runs

### Cache Statistics

| Jobs Cached | Fetch Time | Speed Improvement |
|-------------|------------|-------------------|
| 4,807 / 4,807 | ~5 seconds | **180x faster** |
| 4,800 / 4,807 | ~15 seconds | **360x faster** |
| 0 / 4,807 | ~1.5 hours | Baseline |

## Requirements

- Python 3.8+
- Chrome browser installed
- Dependencies:
  ```bash
  pip install playwright requests
  playwright install chromium
  ```

## Output Statistics

Current scrape (2026-01-17):
- **Total jobs**: 4,807
- **File size**: 24 MB
- **Company**: Tesla
- **Locations**: 700+ worldwide
- **Departments**: Engineering, Manufacturing, Sales, Service, Energy, AI, etc.

## Notes

- **Bot Detection**: Tesla uses Akamai Bot Manager - script handles this automatically
- **Browser Required**: Uses real browser (Playwright) to bypass detection
- **Rate Limiting**: Built-in - fetches ~1 job/second
- **Error Handling**: Continues on errors, saves progress periodically
- **Cache Safety**: Checkpoint saves every 50 jobs prevent data loss
