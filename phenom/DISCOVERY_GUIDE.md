# Phenom Discovery Guide

Practical guide for discovering new Phenom companies.

## Quick Start

### Option A: TheirStack List (Recommended - 156 companies)

**Step 1:** Visit [TheirStack Phenom List](https://theirstack.com/en/technology/phenom-people)

**Step 2:** Create a text file with companies (one per line):

```bash
cat > phenom/companies_to_check.txt << 'EOF'
# TheirStack Phenom Companies - Sample
Gamestop, https://careers.gamestop.com
Thomson Reuters, https://jobs.thomsonreuters.com
Philips
Truist Bank
Citrix
Walmart
IBM
Intel
EOF
```

**Step 3:** Run the discovery script:

```bash
python phenom/discover_from_theirstack.py phenom/companies_to_check.txt
```

The script will:
- ✅ Detect if each site uses Phenom
- ✅ Extract locale and country automatically
- ⚠️ Prompt you for company_code (if not found automatically)
- ✅ Generate `discovered_companies.csv`

**Step 4:** Review and merge:

```bash
# Review the discovered companies
cat phenom/discovered_companies.csv

# Merge into main CSV
cat phenom/discovered_companies.csv | tail -n +2 >> phenom/companies.csv

# Scrape the new companies
python phenom/main.py
```

### Option B: Known Customer Research

Research Phenom's known customers and validate their sites.

**Known Phenom Customers:**
- Gamestop
- Thomson Reuters
- Philips
- Truist Bank
- Citrix
- Walmart
- IBM
- Intel
- GE Healthcare (already configured)
- Bell Canada (already configured)

**Process:**

1. **Find the careers page:**
   ```bash
   # Google: "[Company] careers"
   # Common patterns:
   # - careers.[company].com
   # - jobs.[company].com
   # - www.[company].com/careers
   ```

2. **Detect Phenom:**
   ```bash
   python phenom/detect_phenom.py https://careers.example.com -v
   ```

3. **Extract config:**
   ```bash
   python phenom/extract_company_config.py https://careers.example.com
   ```

4. **Add to CSV** (manually or with `--append-to-csv`)

### Option C: Manual Search + Detection

Search for sites and validate them.

**Step 1:** Search for potential Phenom sites

```bash
# Use search engines to find:
# - "powered by Phenom careers"
# - Companies in specific industries that commonly use Phenom
#   (retail, healthcare, technology, financial services)
```

**Step 2:** Test each URL

```bash
python phenom/detect_phenom.py https://suspected-site.com
```

**Step 3:** If detected, extract config and add to CSV

## Detailed Walkthrough

### Method 1: TheirStack Discovery (Full Process)

#### Step 1: Get TheirStack List

Visit: https://theirstack.com/en/technology/phenom-people

You'll see:
- **Total companies:** 156
- **By country:** US (62), Canada (4), India (1), etc.
- **By industry:** Technology, Healthcare, Retail, Finance, etc.

**Manual Compilation:**

Option 1 - Copy company names manually:
- Click through the pages
- Copy company names to a text file
- Add careers URLs if known

Option 2 - Use browser automation (advanced):
```bash
# If you have Playwright/Selenium, you could scrape the list
# But manual is fine for 156 companies (30 minutes of work)
```

#### Step 2: Create Input File

Create `phenom/theirstack_companies.txt`:

```
# Fortune 500 Companies
Gamestop, https://careers.gamestop.com
Walmart, https://careers.walmart.com
Thomson Reuters, https://jobs.thomsonreuters.com

# Healthcare
Philips, https://www.careers.philips.com
GE Healthcare, https://careers.gehealthcare.com

# Financial Services
Truist Bank, https://careers.truist.com
PNC Bank

# Technology
Citrix
IBM, https://www.ibm.com/careers
Intel, https://jobs.intel.com

# Add more from TheirStack...
```

Format:
- `Company Name` (required)
- `, https://careers.url.com` (optional)
- Lines starting with `#` are ignored (comments)

#### Step 3: Run Discovery

```bash
python phenom/discover_from_theirstack.py phenom/theirstack_companies.txt
```

**Interactive Process:**

For each company, the script will:

1. **Detect Phenom** (automatic)
   ```
   Processing: Gamestop
   1. Detecting Phenom at https://careers.gamestop.com...
   ✓ Found Phenom cookies
   ✓ Found Phenom reference in HTML
   ✓ Phenom detected with high confidence
   ```

2. **Extract config** (mostly automatic)
   ```
   2. Extracting configuration...
   ✓ Found page at /en/us/search-results
   ✓ Extracted locale: en_us
   ✓ Extracted country: us
   ```

3. **Request company_code** (if not found automatically)
   ```
   ⚠ WARNING: Company code not found!

   Manual extraction required:
   1. Visit: https://careers.gamestop.com
   2. Open DevTools (F12) → Network tab
   3. Search for a job
   4. Find POST /widgets request
   5. Look for company code in request/page source

   Enter company code (or press Enter to skip):
   ```

   **How to find company_code:**

   a. Open the careers site in browser
   b. Press F12 (DevTools)
   c. Go to Network tab
   d. Click "Clear" to start fresh
   e. Search for any job on the site
   f. Look for `POST /widgets` request (filter by XHR)
   g. Click on it → "Payload" tab
   h. The payload won't show company_code, but...
   i. Go to "Response" tab → look for company identifier
   j. OR right-click page → "View Page Source"
   k. Search for: `companyCode`, `company_code`, or similar
   l. You'll see something like: `companyCode: "GMSTOPUS"`
   m. Enter: `GMSTOPUS`

4. **Result saved**
   ```
   ✓ Configuration extracted:
     Company: Gamestop
     URL: https://careers.gamestop.com
     Company Code: GMSTOPUS
     Locale: en_us
     Country: us
   ✓ Added Gamestop
   ```

#### Step 4: Review Results

```bash
cat phenom/discovered_companies.csv
```

Output:
```csv
url,name,company_code,locale,country
https://careers.gamestop.com,Gamestop,GMSTOPUS,en_us,us
https://jobs.thomsonreuters.com,Thomson Reuters,TREUTGLOBAL,en_global,global
https://www.careers.philips.com,Philips,PHILIPSGLOBAL,en_global,global
```

#### Step 5: Merge into Main CSV

```bash
# Backup first
cp phenom/companies.csv phenom/companies.csv.backup

# Append new companies (skip header)
tail -n +2 phenom/discovered_companies.csv >> phenom/companies.csv

# Verify
cat phenom/companies.csv
```

#### Step 6: Scrape New Companies

```bash
python phenom/main.py
```

### Method 2: One-by-One Manual Discovery

For adding individual companies:

#### Example: Adding Gamestop

**Step 1:** Find careers page
```
Google: "gamestop careers"
Result: https://careers.gamestop.com
```

**Step 2:** Detect Phenom
```bash
python phenom/detect_phenom.py https://careers.gamestop.com -v
```

Output:
```
============================================================
PHENOM DETECTION RESULT
============================================================
URL: https://careers.gamestop.com
Phenom Detected: Yes
Confidence: high

Detected Signals (4):
  • Phenom cookies: PLAY_SESSION, PHPPPE_ACT
  • Phenom reference in HTML
  • Phenom JavaScript detected
  • /widgets endpoint exists
============================================================
```

**Step 3:** Extract config
```bash
python phenom/extract_company_config.py https://careers.gamestop.com
```

Output:
```
============================================================
EXTRACTED CONFIGURATION
============================================================
Base URL: https://careers.gamestop.com
Company Code: NOT FOUND
Locale: en_us
Country: us
Confidence: low

⚠ WARNING: Company code not found!
Please manually extract it from DevTools:
1. Visit the career site
2. Open DevTools → Network tab
3. Search for jobs
4. Find POST /widgets request
5. Look for company code in the request
============================================================
```

**Step 4:** Manually extract company_code

1. Open https://careers.gamestop.com
2. Press F12 → Network tab
3. Search for "manager" (any job)
4. Find POST to `/widgets`
5. Check Payload tab:
   ```json
   {
     "lang": "en_us",
     "country": "us",
     "pageName": "search-results",
     ...
   }
   ```
6. View Response or check page source
7. Find: `companyCode: "GMSTOPUS"` or similar

**Step 5:** Add to CSV manually

```bash
echo "https://careers.gamestop.com,Gamestop,GMSTOPUS,en_us,us" >> phenom/companies.csv
```

**Step 6:** Test scraping

```bash
python phenom/main.py https://careers.gamestop.com
```

## Tips & Tricks

### Finding Company Codes

**Method 1: Page Source (Easiest)**
1. Visit careers page
2. Right-click → View Page Source
3. Ctrl+F search for: `companyCode`
4. Look for: `"companyCode":"XXXXX"` or `companyCode: "XXXXX"`

**Method 2: Network Tab**
1. F12 → Network tab
2. Search for a job
3. Find POST /widgets request
4. Check Headers, Payload, Response for company identifier

**Method 3: Cookies**
1. F12 → Application → Cookies
2. Look for custom cookies with company identifiers
3. Sometimes stored in cookie values

**Method 4: HAR File**
1. F12 → Network tab → Export HAR
2. Save HAR file
3. Run: `python phenom/extract_company_config.py --har file.har`

### Common Locale/Country Patterns

| Site Domain | Locale | Country |
|-------------|--------|---------|
| `.com` | en_us | us |
| `.ca` or `/ca/` | en_ca | ca |
| `.uk` or `/uk/` | en_uk | uk |
| `global` in URL | en_global | global |
| `.fr` or `/fr/` | fr_fr | fr |
| `.de` or `/de/` | de_de | de |

### Batch Processing Tips

**For 156 TheirStack companies:**

1. **Split the work:**
   - Process 10-20 companies at a time
   - Take breaks (rate limiting)

2. **Prioritize:**
   - Start with largest companies (more jobs)
   - Focus on your target industries/regions

3. **Automate company_code later:**
   - Initial run: skip companies without auto-detected codes
   - Come back later to manually extract codes
   - Use `--append-to-csv` to add them incrementally

4. **Quality over quantity:**
   - Better to have 20 companies with correct configs
   - Than 100 companies with wrong configs

## Industry-Specific Discovery

### Healthcare

Phenom is popular in healthcare:
- GE Healthcare ✅ (already configured)
- Philips
- Johnson & Johnson
- Medtronic
- Abbott Labs

### Retail

Many retail companies use Phenom:
- Gamestop
- Walmart
- Best Buy
- Target

### Financial Services

Banks and financial institutions:
- Truist Bank
- PNC Bank
- TD Bank
- BMO

### Technology

Tech companies using Phenom:
- IBM
- Intel
- Citrix
- Thomson Reuters

## Troubleshooting

### "Could not find careers URL"

**Problem:** Script can't find the careers page
**Solution:** Manually find the URL and specify it:
```
Company Name, https://actual-careers-url.com
```

### "Phenom detected: No"

**Problem:** Site doesn't use Phenom
**Solution:**
1. Double-check the URL (might be wrong page)
2. Try different career page paths
3. Company might have switched platforms
4. TheirStack data might be outdated

### "Company code not found"

**Problem:** Automatic extraction failed
**Solution:**
1. Use manual extraction method (DevTools)
2. Check page source for `companyCode`
3. Try HAR file method
4. Skip for now, add later

### Script hangs or times out

**Problem:** Site is slow or blocking
**Solution:**
1. Increase timeout in code
2. Skip problematic sites
3. Try at different time
4. Check your IP isn't rate-limited

## Next Steps After Discovery

### 1. Verify Configurations

```bash
# Test scraping a few companies
python phenom/main.py https://careers.example.com

# Check output
cat phenom/companies/careers.example.com.json | jq '.jobs | length'
```

### 2. Batch Scrape All

```bash
python phenom/main.py
```

### 3. Export to CSV

```bash
python phenom/export_to_csv.py
```

### 4. Validate Job URLs

```bash
# Check if job URLs are correct
head phenom/jobs.csv

# Test a few URLs in browser
# If format is wrong, update construct_job_url() in export_to_csv.py
```

## Monitoring & Maintenance

### Continuous Discovery

1. **Monitor TheirStack** for new Phenom adoptions
2. **Check industry news** for companies switching to Phenom
3. **Validate existing companies** periodically (they might change platforms)

### Re-scraping Schedule

```bash
# Jobs should be re-scraped every 12 hours (automatic)
# Force re-scrape if needed:
python phenom/main.py --force
```

## Estimated Time

### TheirStack Full Discovery (156 companies)

- **Compile list:** 30 minutes
- **Run discovery script:** 2-4 hours (with manual company_code entry)
- **Total:** ~4-5 hours for complete dataset

### Per Company (Manual)

- **Find careers URL:** 1-2 minutes
- **Detect Phenom:** 30 seconds
- **Extract config:** 2-3 minutes (with manual company_code)
- **Total:** ~5 minutes per company

### Quick Start (Top 20 companies)

- **Select 20 largest/most relevant:** 10 minutes
- **Process with script:** 1-2 hours
- **Total:** ~2 hours for meaningful dataset

## Summary

**Best approach for most users:**
1. Get TheirStack list (156 companies)
2. Use `discover_from_theirstack.py` script
3. Manually extract company_codes as needed
4. Build comprehensive CSV over time

**Quick approach for immediate value:**
1. Focus on top 20 companies in your target industries
2. Manual discovery with detection tools
3. Get high-quality dataset quickly

**Ongoing approach:**
1. Start with known customers
2. Add companies incrementally
3. Validate and maintain configurations
