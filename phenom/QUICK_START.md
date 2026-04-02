# Phenom Discovery - Quick Start

**Fastest way to add Phenom companies - 5 minutes per company**

## Why Manual is Faster

The automated discovery scripts make network requests that can be slow or timeout. The manual workflow is actually **faster and more reliable**.

## Step-by-Step Workflow

### Example: Adding Gamestop

#### Step 1: Check if it's Phenom (30 seconds)

**Visit:** https://careers.gamestop.com

**Look for these signs:**
- Search for a job
- Does the URL change to something like `/en/us/search-results`?
- Open DevTools (F12) → Network tab
- See any requests to `/widgets`?
- See cookies like `PLAY_SESSION` or `PHPPPE_ACT`?

✅ **If yes = It's Phenom**

#### Step 2: Find Company Code (2 minutes)

**Method A: Page Source (Fastest)**

1. On careers page, right-click → "View Page Source"
2. Press Ctrl+F (or Cmd+F)
3. Search for: `companyCode`
4. Find something like: `"companyCode":"GMSTOPUS"` or `companyCode: "GMSTOPUS"`
5. Copy the code: `GMSTOPUS`

**Method B: DevTools Network**

1. Stay on careers page, F12 → Network tab
2. Click "Clear" to start fresh
3. Search for any job (type "manager" and search)
4. Find the POST request to `/widgets`
5. Click it → "Payload" tab
6. Note the `lang` and `country` values:
   ```json
   {
     "lang": "en_us",
     "country": "us",
     ...
   }
   ```
7. Go back to page source to find company code

#### Step 3: Add to CSV (10 seconds)

```bash
# Open the CSV file
nano phenom/companies.csv

# Or use echo to append:
echo "https://careers.gamestop.com,Gamestop,GMSTOPUS,en_us,us" >> phenom/companies.csv
```

**CSV Format:**
```csv
url,name,company_code,locale,country
https://careers.gamestop.com,Gamestop,GMSTOPUS,en_us,us
```

#### Step 4: Test (2 minutes)

```bash
python phenom/main.py https://careers.gamestop.com
```

**Expected output:**
```
Company 'careers.gamestop.com' data file does not exist. I will scrape.
Initializing Phenom client for careers.gamestop.com...
Successfully scraped 123 jobs from careers.gamestop.com
```

✅ **Done!** You just added a new company.

## Known Companies to Try

Here are companies we know use Phenom (try these first):

### Easy Wins (Already Verified)

| Company | URL | Notes |
|---------|-----|-------|
| Bell Canada | https://jobs.bell.ca | ✅ Already configured |
| GE Healthcare | https://careers.gehealthcare.com | ✅ Already configured |

### High Probability (From TheirStack)

| Company | URL to Try | Industry |
|---------|-----------|----------|
| Gamestop | https://careers.gamestop.com | Retail |
| Walmart | https://careers.walmart.com | Retail |
| IBM | https://www.ibm.com/careers | Technology |
| Thomson Reuters | https://jobs.thomsonreuters.com | Technology |
| Philips | https://www.careers.philips.com | Healthcare |
| Truist Bank | https://careers.truist.com | Finance |
| Intel | https://jobs.intel.com | Technology |
| Best Buy | https://jobs.bestbuy.com | Retail |

## Common Patterns

### Company Code Patterns

```
Format: Usually ALL CAPS, often combines company abbreviation + country

Examples:
- BECACA = Bell Canada (CA)
- GEVGHLGLOBAL = GE Healthcare Global
- GMSTOPUS = Gamestop US (example)
- WALMARTUS = Walmart US (example)
- IBMGLOBAL = IBM Global (example)
```

### Locale/Country Patterns

| Your Finding | Locale | Country |
|--------------|--------|---------|
| .com domain, "en_us" in payload | en_us | us |
| .ca domain, "en_ca" in payload | en_ca | ca |
| .uk domain, "en_uk" in payload | en_uk | uk |
| "global" in URL | en_global | global |

## Batch Adding (10 companies in 1 hour)

### Prepare a Checklist

Create `phenom/my_companies.txt`:

```
[ ] Gamestop - https://careers.gamestop.com
[ ] Walmart - https://careers.walmart.com
[ ] IBM - https://www.ibm.com/careers
[ ] Thomson Reuters - https://jobs.thomsonreuters.com
[ ] Philips - https://www.careers.philips.com
```

### For Each Company:

1. Visit URL (check if it's Phenom)
2. Find company code (2 min)
3. Add to CSV (10 sec)
4. Test scraping (2 min)
5. ✅ Check off

**Total time:** ~5 minutes per company

### Then Scrape All

```bash
# After adding 10 companies to CSV
python phenom/main.py

# Export to CSV
python phenom/export_to_csv.py

# Check results
wc -l phenom/jobs.csv
```

## Troubleshooting

### "I can't find the company code"

**Try these:**

1. **Search page source more broadly:**
   - Search for: `company`
   - Search for: `tenant`
   - Search for: `client`
   - Look for patterns like: `"XXX":` or `code: "XXX"`

2. **Check JavaScript files:**
   - In DevTools → Sources tab
   - Look for config.js or similar
   - Search those files for company identifiers

3. **Check cookies:**
   - DevTools → Application → Cookies
   - Look for custom cookie values

4. **Last resort - Skip for now:**
   - Mark as "needs code" in your checklist
   - Move to next company
   - Come back later

### "Site doesn't look like Phenom"

**Check these:**
- Does job search go to `/search-results`?
- Are there cookies like `PLAY_SESSION`?
- Is there a `/widgets` endpoint?

If none of these exist, it's probably not Phenom.

### "Scraping fails with wrong config"

Double-check:
- ✅ Company code is correct (check page source again)
- ✅ Locale matches what you saw in /widgets payload
- ✅ Country matches locale (en_us → us, en_ca → ca)

## Real Example: Step by Step

Let me walk through adding Walmart:

```bash
# 1. Visit https://careers.walmart.com
# 2. Search for a job
# 3. F12 → Network → Find /widgets POST request
# 4. Payload shows:
#    {
#      "lang": "en_us",
#      "country": "us",
#      ...
#    }
# 5. View Page Source → Search "companyCode"
# 6. Find: "companyCode":"WALMARTUS"
# 7. Add to CSV:

echo "https://careers.walmart.com,Walmart,WALMARTUS,en_us,us" >> phenom/companies.csv

# 8. Test:
python phenom/main.py https://careers.walmart.com

# ✅ Should scrape successfully
```

## Automated Tools (Optional)

If you still want to use the automated tools:

### Single Company Detection

```bash
# This checks if a site uses Phenom
python phenom/detect_phenom.py https://careers.example.com -v

# Note: This can be slow (30-60 seconds)
# Often faster to just check manually
```

### Config Extraction

```bash
# This tries to extract locale/country
python phenom/extract_company_config.py https://careers.example.com

# Note: Usually can't find company_code automatically
# You'll still need to find it manually
```

### Batch Discovery

```bash
# Process a list of companies
python phenom/discover_from_theirstack.py phenom/sample_companies_to_check.txt

# Note: Can take 1+ hours for large lists
# Better for batch processing 20+ companies
```

## Next Steps

### Start Small (Today)

1. Pick 3-5 companies from the table above
2. Add them manually (30 minutes total)
3. Scrape them all
4. Verify job data looks good

### Scale Up (This Week)

1. Visit TheirStack: https://theirstack.com/en/technology/phenom-people
2. Pick your top 20 companies
3. Add them over a few days
4. Build your dataset

### Full Coverage (Long Term)

1. Process all 156 companies from TheirStack
2. Use batch tools for efficiency
3. Maintain and update regularly

## Summary

**Recommended Workflow:**
1. ✅ Manual is faster than automated (2-5 min per company)
2. ✅ Start with known companies from the list above
3. ✅ Add 5-10 companies to get comfortable
4. ✅ Then scale up with batch tools if needed

**Key Files:**
- Add companies to: `phenom/companies.csv`
- Scrape with: `python phenom/main.py`
- Export with: `python phenom/export_to_csv.py`

**Need Help?**
- Read: `phenom/README.md`
- Cheatsheet: `phenom/DISCOVERY_CHEATSHEET.md`
- Full guide: `phenom/DISCOVERY_GUIDE.md`
