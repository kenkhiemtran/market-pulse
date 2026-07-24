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
