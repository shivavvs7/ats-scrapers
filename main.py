from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
import jobhive

app = FastAPI()

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>JobHive Board</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #f5f5f4; color: #1c1c1a; }
    header { background: #fff; border-bottom: 1px solid #e5e5e3; padding: 1rem 2rem; display: flex; align-items: center; gap: 12px; }
    header h1 { font-size: 1.2rem; font-weight: 600; }
    .search-bar { display: flex; gap: 8px; padding: 1.5rem 2rem; flex-wrap: wrap; }
    .search-bar input, .search-bar select { padding: 8px 12px; border: 1px solid #d4d4d0; border-radius: 8px; font-size: 14px; background: #fff; min-width: 160px; }
    .search-bar button { padding: 8px 20px; background: #1c1c1a; color: #fff; border: none; border-radius: 8px; font-size: 14px; cursor: pointer; }
    .search-bar button:hover { background: #333; }
    .results { padding: 0 2rem 2rem; display: grid; gap: 12px; }
    .job-card { background: #fff; border: 1px solid #e5e5e3; border-radius: 12px; padding: 1rem 1.25rem; }
    .job-card h2 { font-size: 15px; font-weight: 600; margin-bottom: 4px; }
    .job-card .company { font-size: 13px; color: #666; margin-bottom: 8px; }
    .tags { display: flex; gap: 6px; flex-wrap: wrap; }
    .tag { font-size: 11px; padding: 3px 8px; border-radius: 6px; background: #f0f0ee; color: #555; }
    .tag.remote { background: #e6f5ee; color: #1a7a4a; }
    .tag.salary { background: #e6f0fa; color: #1a4a7a; }
    .status { padding: 2rem; color: #888; text-align: center; }
    a.apply { font-size: 12px; margin-top: 10px; display: inline-block; color: #1c1c1a; border: 1px solid #d4d4d0; padding: 4px 10px; border-radius: 6px; text-decoration: none; }
    a.apply:hover { background: #f5f5f4; }
  </style>
</head>
<body>
  <header>
    <h1>🐝 JobHive Board</h1>
    <span style="font-size:13px;color:#888;">Live jobs from 47 ATS platforms</span>
  </header>
  <div class="search-bar">
    <input id="q" type="text" placeholder="Job title, skill..." value="engineer" />
    <select id="ats">
      <option value="">All ATS</option>
      <option value="greenhouse">Greenhouse</option>
      <option value="lever">Lever</option>
      <option value="ashby">Ashby</option>
      <option value="workday">Workday</option>
      <option value="smartrecruiters">SmartRecruiters</option>
    </select>
    <input id="location" type="text" placeholder="Location (e.g. Paris)" />
    <button onclick="search()">Search</button>
  </div>
  <div class="results" id="results">
    <p class="status">Enter a search to find jobs.</p>
  </div>
  <script>
    async function search() {
      const q = document.getElementById('q').value;
      const ats = document.getElementById('ats').value;
      const loc = document.getElementById('location').value;
      document.getElementById('results').innerHTML = '<p class="status">Loading...</p>';
      const params = new URLSearchParams({ query: q });
      if (ats) params.append('ats', ats);
      if (loc) params.append('location', loc);
      const res = await fetch('/api/search?' + params);
      const jobs = await res.json();
      if (!jobs.length) {
        document.getElementById('results').innerHTML = '<p class="status">No results found.</p>';
        return;
      }
      document.getElementById('results').innerHTML = jobs.map(j => `
        <div class="job-card">
          <h2>${j.title}</h2>
          <p class="company">${j.company} &middot; ${j.ats_type}</p>
          <div class="tags">
            ${j.location ? `<span class="tag">${j.location}</span>` : ''}
            ${j.is_remote ? '<span class="tag remote">Remote</span>' : ''}
            ${j.employment_type ? `<span class="tag">${j.employment_type}</span>` : ''}
            ${j.salary_summary ? `<span class="tag salary">${j.salary_summary}</span>` : ''}
          </div>
          ${j.apply_url ? `<a class="apply" href="${j.apply_url}" target="_blank">Apply →</a>` : ''}
        </div>
      `).join('');
    }
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTML

@app.get("/api/search")
def search(
    query: str = Query(...),
    ats: str = Query(None),
    location: str = Query(None),
    limit: int = Query(20)
):
    df = jobhive.search(query=query, ats=ats, location=location)
    df = df.head(limit)
    cols = ["title", "company", "ats_type", "location", "is_remote",
            "employment_type", "salary_summary", "apply_url"]
    df = df[[c for c in cols if c in df.columns]]
    return df.fillna("").to_dict(orient="records")