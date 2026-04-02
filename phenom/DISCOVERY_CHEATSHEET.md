# Phenom Discovery Cheatsheet

Quick reference for discovering Phenom companies.

## 🚀 Quick Start (5 Minutes)

```bash
# 1. Use the sample list
python phenom/discover_from_theirstack.py phenom/sample_companies_to_check.txt

# 2. The script will prompt you for company codes when needed

# 3. Review results
cat phenom/discovered_companies.csv

# 4. Merge into main CSV
tail -n +2 phenom/discovered_companies.csv >> phenom/companies.csv

# 5. Scrape
python phenom/main.py
```

## 🔍 Discovery Methods

### Method 1: TheirStack (156 companies) ⭐ RECOMMENDED

```bash
# Create list from https://theirstack.com/en/technology/phenom-people
cat > phenom/companies_to_check.txt << 'EOF'
Gamestop, https://careers.gamestop.com
Thomson Reuters, https://jobs.thomsonreuters.com
Philips
EOF

# Run discovery
python phenom/discover_from_theirstack.py phenom/companies_to_check.txt
```

### Method 2: Single Company

```bash
# Detect
python phenom/detect_phenom.py https://careers.example.com -v

# Extract config
python phenom/extract_company_config.py https://careers.example.com

# Add to CSV
echo "https://careers.example.com,Company Name,COMPANYCODE,en_us,us" >> phenom/companies.csv

# Test
python phenom/main.py https://careers.example.com
```

### Method 3: Known Customers

Known Phenom users:
- **Retail:** Gamestop, Walmart, Best Buy, Target
- **Tech:** IBM, Intel, Citrix, Thomson Reuters
- **Healthcare:** Philips, J&J, Medtronic, Abbott
- **Finance:** Truist, PNC, TD Bank, BMO

## 📝 Finding Company Code (Manual)

### Method A: Page Source (Easiest) ⭐

```bash
1. Visit careers page
2. Right-click → "View Page Source"
3. Ctrl+F search: "companyCode"
4. Find: "companyCode":"XXXXX"
```

### Method B: DevTools Network Tab

```bash
1. Open careers page
2. Press F12 → Network tab
3. Click "Clear"
4. Search for any job
5. Find: POST /widgets
6. Click → Payload tab
7. Note: lang (locale), country
8. Check Response tab or page source for company code
```

### Method C: HAR File

```bash
1. F12 → Network tab
2. Click export (download icon)
3. Save as traffic.har
4. python phenom/extract_company_config.py --har traffic.har
```

## 🎯 Common Patterns

### URL Patterns

```
careers.[company].com     ← Most common
jobs.[company].com
[company].com/careers
work.at.[company].com
```

### Locale/Country

| Domain | Locale | Country |
|--------|--------|---------|
| `.com` | en_us | us |
| `.ca` | en_ca | ca |
| `.uk` | en_uk | uk |
| `global` | en_global | global |

### Company Code Format

```
Usually ALL CAPS
Examples:
- BECACA (Bell Canada)
- GEVGHLGLOBAL (GE Healthcare)
- GMSTOPUS (Gamestop example)
```

## 🔧 Commands Reference

### Detection

```bash
# Basic detection
python phenom/detect_phenom.py https://careers.example.com

# Verbose (shows all checks)
python phenom/detect_phenom.py https://careers.example.com -v

# Batch detect
for url in $(cat urls.txt); do
  python phenom/detect_phenom.py $url
done
```

### Config Extraction

```bash
# Automatic extraction
python phenom/extract_company_config.py https://careers.example.com

# From HAR file
python phenom/extract_company_config.py --har traffic.har

# Extract and append to CSV (interactive)
python phenom/extract_company_config.py https://careers.example.com --append-to-csv
```

### Batch Discovery

```bash
# Process list of companies
python phenom/discover_from_theirstack.py companies.txt

# With custom output
python phenom/discover_from_theirstack.py companies.txt -o output.csv
```

### Scraping

```bash
# Scrape all
python phenom/main.py

# Scrape one
python phenom/main.py https://careers.example.com

# Force re-scrape (ignore cache)
python phenom/main.py --force

# Export to CSV
python phenom/export_to_csv.py
```

## ✅ Verification

```bash
# Check detection worked
cat phenom/discovered_companies.csv

# Verify scraping worked
cat phenom/companies/careers.example.com.json | jq '.jobs | length'

# Check CSV output
head phenom/jobs.csv
wc -l phenom/jobs.csv

# Test a job URL in browser
# Should open the job application page
```

## 📊 Expected Output

### Detection (Positive)

```
Phenom Detected: Yes
Confidence: high
Detected Signals (4):
  • Phenom cookies: PLAY_SESSION, PHPPPE_ACT
  • Phenom reference in HTML
  • /widgets endpoint exists
```

### Config Extraction

```
Base URL: https://careers.example.com
Company Code: EXAMPLECO
Locale: en_us
Country: us

CSV Entry:
https://careers.example.com,COMPANY_NAME,EXAMPLECO,en_us,us
```

### Scraping

```
Successfully scraped 427 jobs from careers.example.com
Total runtime: 8.45 seconds
```

## ⚠️ Troubleshooting

### "Company code not found"

```bash
# Solution: Manual extraction required
# Follow Method A (Page Source) or Method B (DevTools) above
```

### "Phenom detected: No"

```bash
# Check:
# 1. Is the URL correct? (try different paths)
# 2. Does the site actually use Phenom?
# 3. Is the site blocking automated requests?
```

### "No jobs found"

```bash
# Check:
# 1. Wrong company_code → verify in DevTools
# 2. Wrong locale/country → check /widgets payload
# 3. Company has no open positions → verify on site
```

### Timeout or hang

```bash
# Solution: Add delay, skip problematic sites
# Or check if your IP is rate-limited
```

## 📈 Time Estimates

| Task | Time |
|------|------|
| Single company (manual) | 5 min |
| 20 companies (script) | 2 hours |
| 156 companies (full TheirStack) | 4-5 hours |

## 🎓 Learning Path

### Beginner (Start Here)

```bash
# 1. Test with known company
python phenom/detect_phenom.py https://jobs.bell.ca -v

# 2. Try extracting config
python phenom/extract_company_config.py https://jobs.bell.ca

# 3. Add one new company manually
```

### Intermediate

```bash
# 1. Use sample list
python phenom/discover_from_theirstack.py phenom/sample_companies_to_check.txt

# 2. Process 10-20 companies
# 3. Master company_code extraction
```

### Advanced

```bash
# 1. Get full TheirStack list (156 companies)
# 2. Process entire list
# 3. Build comprehensive dataset
# 4. Automate maintenance
```

## 🔗 Resources

- **TheirStack List:** https://theirstack.com/en/technology/phenom-people
- **Full Guide:** phenom/DISCOVERY_GUIDE.md
- **README:** phenom/README.md
- **Sample List:** phenom/sample_companies_to_check.txt

## 💡 Pro Tips

1. **Start small:** Process 10-20 companies first
2. **Prioritize:** Focus on industries you care about
3. **Quality > Quantity:** Better to have correct configs
4. **Use samples:** Start with sample_companies_to_check.txt
5. **Batch work:** Process companies in groups
6. **Take breaks:** Rate limiting is real
7. **Document codes:** Save company_codes as you find them
8. **Test scraping:** Verify each company works before moving on

## 🚨 Common Mistakes

❌ **Adding company without company_code**
```csv
https://careers.example.com,Example Corp,,en_us,us
```
✅ **Always include company_code**
```csv
https://careers.example.com,Example Corp,EXAMPLECO,en_us,us
```

❌ **Wrong URL format**
```csv
careers.example.com,Example Corp,EXAMPLECO,en_us,us
```
✅ **Include https://**
```csv
https://careers.example.com,Example Corp,EXAMPLECO,en_us,us
```

❌ **Skipping verification**
```bash
# Added to CSV, didn't test
```
✅ **Always test after adding**
```bash
python phenom/main.py https://careers.example.com
```

## 📞 Need Help?

1. **Read the guides:**
   - DISCOVERY_GUIDE.md (detailed walkthrough)
   - README.md (comprehensive docs)

2. **Check examples:**
   - Bell Canada and GE Healthcare are working examples
   - See phenom/companies.csv for reference

3. **Debug issues:**
   - Use verbose mode: `-v`
   - Check phenom/companies/*.json files
   - Verify job URLs in browser
