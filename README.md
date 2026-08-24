# Market Pulse — Daily Tech Supply Chain Monitor

Runs every day at 10:00 AM, pulls global tech stock data across the entire supply chain (EDA → equipment → foundry → memory → chip design → networking → cloud → devices → software → distribution) plus industry news from trusted RSS feeds, then:

1. **Appends** every ticker's metrics + a per-segment summary to a Google Sheet (a growing dataset you can analyze later)
2. **Emails** you an HTML digest: segment heatmap, big movers, unusual volume, headline keyword trends, and top headlines

No fragile HTML scraping — it uses the Yahoo Finance API (via `yfinance`) and official RSS feeds, so it won't break when a website redesigns.

---

## 1. Setup (one time, ~15 min)

```bash
cd market_pulse
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
copy .env.example .env       # Windows  (cp on Mac/Linux)
```

### Email (Gmail)
1. Google Account → Security → 2-Step Verification → **App passwords** → create one for "Mail"
2. Put your address and that 16-character password in `.env` (`EMAIL_SENDER`, `EMAIL_APP_PASSWORD`)

### Google Sheet
1. Create a blank Google Sheet, copy its ID from the URL (`docs.google.com/spreadsheets/d/<ID>/edit`) into `.env`
2. Go to [console.cloud.google.com](https://console.cloud.google.com) → create a project → enable **Google Sheets API** and **Google Drive API**
3. IAM & Admin → Service Accounts → create one → Keys → **Add key (JSON)** → save the file as `service_account.json` in this folder
4. Open the JSON, copy the `client_email` value, and **share your Google Sheet with that email** (Editor access)

The script auto-creates two tabs: `daily_log` (one row per ticker per day) and `segment_summary`.

### Google Drive (predictive_model.py report uploads)
Reuses the exact same service account as the Sheet above — its Cloud project already
has the Drive API enabled from step 2, so there's nothing new to create there.
- Optional: set `GOOGLE_DRIVE_FOLDER_ID` in `.env` to a folder you've shared with the
  service account's `client_email` (Editor access, same as the Sheet) to file uploads
  under it.
- Whether or not you set a folder, every upload is also shared directly with
  `EMAIL_SENDER` so it shows up in your own Drive — not just the service account's own
  hidden space.

### Test it
```bash
python market_pulse.py --dry-run   # fetches everything, prints summary, no email/sheet
python market_pulse.py             # full run
```
Every run also saves a local backup in `output/` (CSV + the HTML digest), so nothing is lost even if email or Sheets fails.

---

## 2. Schedule for 10:00 AM daily

### Windows — Task Scheduler
1. Create `run_pulse.bat` in this folder:
   ```bat
   @echo off
   cd /d "%~dp0"
   call venv\Scripts\activate
   python market_pulse.py >> output\run_log.txt 2>&1
   ```
2. Open **Task Scheduler** → Create Basic Task → name it "Market Pulse"
3. Trigger: **Daily**, start time **10:00 AM**
4. Action: **Start a program** → browse to `run_pulse.bat`
5. In task Properties, check **"Run task as soon as possible after a scheduled start is missed"** (covers the case where your laptop was asleep at 10)

### Mac/Linux — cron
```bash
crontab -e
# add:
0 10 * * * cd /path/to/market_pulse && ./venv/bin/python market_pulse.py >> output/run_log.txt 2>&1
```
(On a Mac laptop, `launchd` handles missed runs better than cron — happy to set that up if needed.)

---

## 2b. Monthly supply-chain forecast report

`predictive_model.py` fits a momentum model on `output/stocks_*.csv` and writes
`output/predictions_<date>.csv` + `output/monthly_forecast_<month>.md`.
`render_report.py` builds on that: it re-runs the same forecast, renders the
designed HTML/PDF report (`report_assets/template.html`, fonts cached locally
under `report_assets/fonts/` — no network dependency), and saves the whole
package (HTML, PDF, CSV, MD) into a local folder, default
`~/Downloads/Forecast Report/<YYYY-MM>/`:

```bash
python render_report.py                       # saves to ~/Downloads/Forecast Report/<month>
python render_report.py --dest "D:\Reports"    # or a custom folder
```

PDF export shells out to a local Edge or Chrome install (`--headless=new
--print-to-pdf`). If neither is found, the HTML report is still written — just
open it in a browser.

### Windows — Task Scheduler (already set up)
A monthly task named **MarketPulseMonthlyForecast** runs `run_monthly_report.bat`
on the 1st of each month at 9:00 AM (start-when-available is on, same as the
daily task). To inspect, change, or remove it:
```powershell
Get-ScheduledTask -TaskName "MarketPulseMonthlyForecast"
Unregister-ScheduledTask -TaskName "MarketPulseMonthlyForecast" -Confirm:$false
```
Recreate it (note: `schtasks /TR` breaks on the space in this folder's name —
use the 8.3 short path, from `(New-Object -ComObject Scripting.FileSystemObject).GetFile("<path>").ShortPath`):
```powershell
schtasks /create /TN "MarketPulseMonthlyForecast" /TR "<short-path-to-run_monthly_report.bat>" /SC MONTHLY /D 1 /ST 09:00 /RL LIMITED /F
```

### Google Drive upload — currently disabled
`predictive_model.py` also has an `upload_to_drive()` step (same service account
as the Sheet). It's off by default here (`upload=False`) because **Google
blocks a service account from writing file content to a personal
(non-Workspace) Google Drive** — confirmed via a live 403 "Service Accounts do
not have storage quota," even into a folder shared with it (Shared Drives and
OAuth delegation, Google's suggested fixes, are both Workspace-only features).
It works if you're on Google Workspace (`GOOGLE_DRIVE_FOLDER_ID` env var, see
`.env.example`) — otherwise this is a real platform limitation, not a bug.

---

## 3. Customizing

Everything lives in `config.py`:

- **`SUPPLY_CHAIN`** — add/remove tickers or whole segments. International tickers use Yahoo suffixes (`.KS` Korea, `.T` Tokyo, `.TW` Taiwan, `.HK` Hong Kong)
- **`NEWS_FEEDS`** — add any RSS feed. The Google News query feeds are the easiest way to track a new topic: just change the `q=` parameter
- **`TREND_KEYWORDS`** — the words counted across headlines to surface what the market is discussing
- **`BIG_MOVE_PCT` / `VOLUME_SPIKE_RATIO`** — sensitivity of the "big movers" and "unusual volume" alerts

## Notes & limits

- At 10 AM Pacific, US markets have been open ~30 min, so US "1-day" numbers reflect early trading vs. yesterday's close; Asian and European tickers (TSMC Taiwan, Samsung, Tokyo Electron, ASML) show their completed sessions — which is actually useful: overnight Asia often signals where US chips open.
- `yfinance` is a free community wrapper around Yahoo Finance — fine for daily research use; occasional tickers may fail on a given day (the script skips them and continues).
- Keyword counts and volume flags are descriptive signals for research, not trading advice.
