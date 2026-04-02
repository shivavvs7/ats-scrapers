# Quick Start Guide - Oracle Recruiting Cloud API Client

## Installation (2 minutes)

```bash
# 1. Ensure Python 3.7+ is installed
python --version

# 2. Install required library
pip install requests

# 3. You're ready to go!
```

## Basic Usage (30 seconds)

```python
from api_client import OracleRecruitingClient

# Connect to Oracle's careers site
client = OracleRecruitingClient(
    base_url="https://eeho.fa.us2.oraclecloud.com",
    site_number="CX_45001"
)

# Search for jobs
response = client.search_jobs(keyword="python developer", limit=10)
jobs = client.extract_jobs_from_response(response)

# Print results
for job in jobs:
    print(f"{job['Title']} - {job['PrimaryLocation']}")
```

## Run Examples

```bash
# Run the built-in examples
python api_client.py

# Run comprehensive tests
python test_client.py
```

## Common Tasks

### Search for specific jobs
```python
# By keyword
jobs = client.search_jobs(keyword="data scientist")

# By keyword with location
jobs = client.search_jobs(keyword="engineer", limit=20)

# Sort by relevancy
jobs = client.search_jobs(keyword="cloud", sort_by="RELEVANCY")
```

### Get job details
```python
# Get details for a specific job
details = client.get_job_details(job_id="320918")
```

### Find recruiting events
```python
# Search events
response = client.search_events(limit=10)
events = client.extract_events_from_response(response)

for event in events:
    print(f"{event['Title']} - {event['StartDate']}")
```

### Location autocomplete
```python
# Get location suggestions
suggestions = client.autocomplete_locations("San Francisco")
```

## Using with Other Companies

To use with a different company:

1. **Find their Oracle careers URL** (look for `.oraclecloud.com` in the domain)
2. **Find their site number** (inspect Network tab while searching jobs)
3. **Update the client**:

```python
client = OracleRecruitingClient(
    base_url="https://YOUR-COMPANY.fa.REGION.oraclecloud.com",
    site_number="CX_XXXXX"  # Their specific site number
)
```

## Response Format

Jobs are returned in this format:
```python
{
    'Id': '320918',
    'Title': 'Senior Program Manager',
    'PrimaryLocation': 'United States',
    'PostedDate': '2026-01-25',
    'ShortDescriptionStr': 'Job description...',
    ...
}
```

## Need Help?

- **Full documentation**: See `README.md`
- **Project summary**: See `SUMMARY.md`
- **Test examples**: See `test_client.py`
- **Issues**: Check that base_url and site_number are correct

## Next Steps

1. ✅ Run `python test_client.py` to verify everything works
2. ✅ Read `README.md` for complete API documentation
3. ✅ Check `SUMMARY.md` for technical details
4. ✅ Start building your job search tools!

---

**Pro Tip**: Use `client.extract_jobs_from_response()` to easily get the job list from search results without dealing with the nested response structure.
