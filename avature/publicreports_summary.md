# Avature PublicReports Endpoint Analysis

## Summary

The endpoint pattern `https://{companyId}.avature.net/PublicReports/{id}/json` **exists** but requires authentication for most companies.

## Findings

### Endpoint Status
- ✅ **Endpoint pattern is valid**: The URL structure is correct
- ⚠️ **Authentication required**: Most endpoints return `403 Forbidden` instead of `404 Not Found`
- ❌ **No publicly accessible endpoints found**: All tested endpoints require authentication

### Tested Companies
Tested **32 companies** from `companies.csv` with report IDs: `SearchJobs`, `1`, `100`

### Results
- **93 endpoints** return `403 Forbidden` (endpoint exists, requires auth)
- **0 endpoints** return `200 OK` with valid JSON (publicly accessible)
- **3 endpoints** return `404 Not Found` (endpoint doesn't exist)

## Example Endpoints (Require Authentication)

These endpoints exist but need authentication:

1. `https://astellas.avature.net/PublicReports/SearchJobs/json`
2. `https://barclays.avature.net/PublicReports/SearchJobs/json`
3. `https://bloomberg.avature.net/PublicReports/SearchJobs/json`
4. `https://maximus.avature.net/PublicReports/SearchJobs/json`
5. `https://justicejobs.avature.net/PublicReports/SearchJobs/json`

## How to Access

To use these endpoints, you likely need:

1. **Avature API credentials** - API key or OAuth token
2. **Session authentication** - Log in to the Avature portal first
3. **Correct Report ID** - The report ID may need to be obtained from:
   - Avature admin panel
   - Company-specific configuration
   - Embedded in the careers page HTML/JavaScript

## Next Steps

1. Check Avature admin panel for configured PublicReports
2. Look for report IDs in the HTML source of careers pages
3. Contact Avature support for API access
4. Try accessing with authenticated session cookies

## Test Scripts Created

- `find_publicreports.py` - Comprehensive testing script
- `test_publicreports_quick.py` - Quick test script
- `test_with_session.py` - Test with session cookies
- `find_public_endpoints.py` - Test all companies from CSV
