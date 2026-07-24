"""
Market Pulse — daily tech supply chain monitor
================================================
Pulls global tech stock data (via yfinance) and industry news (via RSS),
builds a trend digest, then:
  1. appends the data to a Google Sheet (running log), and
  2. emails you an HTML digest.

Run manually:   python market_pulse.py
Dry run:        python market_pulse.py --dry-run   (prints digest, skips email/sheet)
Scheduled:      see README.md for Task Scheduler / cron setup (daily 10:00 AM)
"""

import argparse
import os
import re
import smtplib
import ssl
import sys
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

import config

load_dotenv()

TODAY = datetime.now().strftime("%Y-%m-%d")


# ===========================================================================
# 1. STOCK DATA
# ===========================================================================
def fetch_stock_data() -> pd.DataFrame:
    """Download recent history for every ticker and compute trend metrics."""
    all_tickers = [t for ticks in config.SUPPLY_CHAIN.values() for t in ticks]
    ticker_to_segment = {
        t: seg for seg, ticks in config.SUPPLY_CHAIN.items() for t in ticks
    }

    print(f"[stocks] downloading {len(all_tickers)} tickers...")
    raw = yf.download(
        all_tickers,
        period=f"{config.HISTORY_DAYS}d",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    rows = []
    for t in all_tickers:
        try:
            df = raw[t].dropna(subset=["Close"]) if isinstance(raw.columns, pd.MultiIndex) else raw.dropna(subset=["Close"])
            if len(df) < 6:
                print(f"[stocks] insufficient data for {t}, skipping")
                continue

            close = df["Close"]
            vol = df["Volume"]

            last = float(close.iloc[-1])
            chg_1d = (last / float(close.iloc[-2]) - 1) * 100
            chg_5d = (last / float(close.iloc[-6]) - 1) * 100 if len(close) >= 6 else None
            chg_20d = (last / float(close.iloc[-21]) - 1) * 100 if len(close) >= 21 else None

            vol_avg20 = float(vol.iloc[-21:-1].mean()) if len(vol) >= 21 else float(vol.iloc[:-1].mean())
            vol_ratio = float(vol.iloc[-1]) / vol_avg20 if vol_avg20 > 0 else None

            rows.append({
                "date": TODAY,
                "ticker": t,
                "segment": ticker_to_segment[t],
                "close": round(last, 2),
                "chg_1d_pct": round(chg_1d, 2),
                "chg_5d_pct": round(chg_5d, 2) if chg_5d is not None else None,
                "chg_20d_pct": round(chg_20d, 2) if chg_20d is not None else None,
                "volume_vs_20d_avg": round(vol_ratio, 2) if vol_ratio is not None else None,
            })
        except Exception as e:
            print(f"[stocks] failed for {t}: {e}")

    df = pd.DataFrame(rows)
    print(f"[stocks] got data for {len(df)} tickers")
    return df


def build_segment_summary(stocks: pd.DataFrame) -> pd.DataFrame:
    """Average moves per supply chain segment — the big-picture view."""
    if stocks.empty:
        return pd.DataFrame()
    summary = (
        stocks.groupby("segment")
        .agg(
            avg_1d=("chg_1d_pct", "mean"),
            avg_5d=("chg_5d_pct", "mean"),
            avg_20d=("chg_20d_pct", "mean"),
            n_tickers=("ticker", "count"),
        )
        .round(2)
        .reset_index()
        .sort_values("avg_1d", ascending=False)
    )
    summary.insert(0, "date", TODAY)
    return summary


# ===========================================================================
# 2. NEWS
# ===========================================================================
def fetch_news() -> list[dict]:
    """Pull recent articles from all RSS feeds."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.NEWS_LOOKBACK_HOURS)
    articles = []

    for source, url in config.NEWS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries:
                if count >= config.MAX_ARTICLES_PER_FEED:
                    break
                # Parse publish time if available; keep undated entries
                published = None
                for attr in ("published_parsed", "updated_parsed"):
                    tm = getattr(entry, attr, None)
                    if tm:
                        published = datetime(*tm[:6], tzinfo=timezone.utc)
                        break
                if published and published < cutoff:
                    continue

                articles.append({
                    "source": source,
                    "title": entry.get("title", "").strip(),
                    "link": entry.get("link", ""),
                    "published": published.strftime("%Y-%m-%d %H:%M UTC") if published else "recent",
                })
                count += 1
            print(f"[news] {source}: {count} articles")
        except Exception as e:
            print(f"[news] failed for {source}: {e}")

    # De-duplicate near-identical headlines (common with Google News feeds)
    seen, unique = set(), []
    for a in articles:
        key = re.sub(r"\W+", "", a["title"].lower())[:60]
        if key and key not in seen:
            seen.add(key)
            unique.append(a)
    print(f"[news] {len(unique)} unique articles after de-dup")
    return unique


def keyword_trends(articles: list[dict]) -> list[tuple[str, int]]:
    """Count tracked keywords across headlines — what is the market talking about?"""
    counter = Counter()
    for a in articles:
        title_lower = a["title"].lower()
        for kw in config.TREND_KEYWORDS:
            if kw.lower() in title_lower:
                counter[kw] += 1
    return counter.most_common(12)


# ===========================================================================
# 3. INSIGHTS
# ===========================================================================
def build_insights(stocks: pd.DataFrame, articles: list[dict]) -> dict:
    ins = {"movers_up": [], "movers_down": [], "volume_spikes": [], "keywords": []}
    if not stocks.empty:
        big = stocks[stocks["chg_1d_pct"].abs() >= config.BIG_MOVE_PCT]
        ins["movers_up"] = big[big["chg_1d_pct"] > 0].sort_values("chg_1d_pct", ascending=False).to_dict("records")
        ins["movers_down"] = big[big["chg_1d_pct"] < 0].sort_values("chg_1d_pct").to_dict("records")
        spikes = stocks[stocks["volume_vs_20d_avg"] >= config.VOLUME_SPIKE_RATIO]
        ins["volume_spikes"] = spikes.sort_values("volume_vs_20d_avg", ascending=False).to_dict("records")
    ins["keywords"] = keyword_trends(articles)
    return ins


# ===========================================================================
# 4. EMAIL DIGEST
# ===========================================================================
def render_email_html(stocks, summary, articles, insights) -> str:
    def pct_cell(v):
        if v is None or pd.isna(v):
            return "<td>—</td>"
        color = "#0a7d33" if v > 0 else ("#c0392b" if v < 0 else "#555")
        return f'<td style="color:{color};font-weight:600">{v:+.2f}%</td>'

    h = [f"""
    <html><body style="font-family:Segoe UI,Arial,sans-serif;color:#222;max-width:760px;margin:auto">
    <h2 style="border-bottom:3px solid #2c5f8a;padding-bottom:6px">Tech Supply Chain Pulse — {TODAY}</h2>
    """]

    # Segment summary
    if not summary.empty:
        h.append('<h3 style="color:#2c5f8a">📦 Supply Chain Segments (avg move)</h3>')
        h.append('<table cellpadding="6" style="border-collapse:collapse;width:100%;font-size:14px">')
        h.append('<tr style="background:#2c5f8a;color:#fff;text-align:left"><th>Segment</th><th>1-Day</th><th>5-Day</th><th>20-Day</th></tr>')
        for i, r in summary.iterrows():
            bg = "#f5f8fb" if i % 2 else "#fff"
            h.append(f'<tr style="background:{bg}"><td>{r["segment"]}</td>{pct_cell(r["avg_1d"])}{pct_cell(r["avg_5d"])}{pct_cell(r["avg_20d"])}</tr>')
        h.append("</table>")

    # Big movers
    if insights["movers_up"] or insights["movers_down"]:
        h.append('<h3 style="color:#2c5f8a">🚀 Big Movers (±%.1f%%+)</h3><ul style="font-size:14px">' % config.BIG_MOVE_PCT)
        for m in insights["movers_up"][:8]:
            h.append(f'<li><b>{m["ticker"]}</b> ({m["segment"]}): <span style="color:#0a7d33">{m["chg_1d_pct"]:+.2f}%</span></li>')
        for m in insights["movers_down"][:8]:
            h.append(f'<li><b>{m["ticker"]}</b> ({m["segment"]}): <span style="color:#c0392b">{m["chg_1d_pct"]:+.2f}%</span></li>')
        h.append("</ul>")

    # Volume spikes
    if insights["volume_spikes"]:
        h.append('<h3 style="color:#2c5f8a">📈 Unusual Volume (institutional attention)</h3><ul style="font-size:14px">')
        for v in insights["volume_spikes"][:8]:
            h.append(f'<li><b>{v["ticker"]}</b> ({v["segment"]}): {v["volume_vs_20d_avg"]}x normal volume, {v["chg_1d_pct"]:+.2f}%</li>')
        h.append("</ul>")

    # Keyword trends
    if insights["keywords"]:
        h.append('<h3 style="color:#2c5f8a">🔍 What the news is talking about</h3><p style="font-size:14px">')
        h.append(" · ".join(f"<b>{k}</b> ({c})" for k, c in insights["keywords"]))
        h.append("</p>")

    # Headlines
    if articles:
        h.append('<h3 style="color:#2c5f8a">📰 Headlines (last %dh)</h3><ul style="font-size:13px;line-height:1.6">' % config.NEWS_LOOKBACK_HOURS)
        for a in articles[:30]:
            h.append(f'<li><a href="{a["link"]}" style="color:#2c5f8a;text-decoration:none">{a["title"]}</a> <span style="color:#888">— {a["source"]}</span></li>')
        h.append("</ul>")

    h.append('<p style="color:#999;font-size:11px">Automated by Market Pulse. Data: Yahoo Finance & public RSS feeds. For research only — not investment advice.</p>')
    h.append("</body></html>")
    return "".join(h)


def send_email(html: str) -> None:
    sender = os.getenv("EMAIL_SENDER")
    password = os.getenv("EMAIL_APP_PASSWORD")
    recipient = os.getenv("EMAIL_RECIPIENT", sender)
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "465"))

    if not sender or not password:
        print("[email] EMAIL_SENDER / EMAIL_APP_PASSWORD not set — skipping email")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{config.EMAIL_SUBJECT_PREFIX} — {TODAY}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=ctx) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient.split(","), msg.as_string())
    print(f"[email] digest sent to {recipient}")


# ===========================================================================
# 5. GOOGLE SHEETS
# ===========================================================================
def append_to_sheets(stocks: pd.DataFrame, summary: pd.DataFrame) -> None:
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    creds_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")

    if not sheet_id:
        print("[sheets] GOOGLE_SHEET_ID not set — skipping Google Sheets")
        return
    if not os.path.exists(creds_path):
        print(f"[sheets] credentials file not found at {creds_path} — skipping")
        return

    import gspread
    gc = gspread.service_account(filename=creds_path)
    sh = gc.open_by_key(sheet_id)

    def get_or_create(tab, headers):
        try:
            ws = sh.worksheet(tab)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=tab, rows=1000, cols=len(headers))
            ws.append_row(headers)
        return ws

    if not stocks.empty:
        ws = get_or_create(config.SHEET_TAB_DAILY, list(stocks.columns))
        ws.append_rows(stocks.fillna("").values.tolist(), value_input_option="USER_ENTERED")
        print(f"[sheets] appended {len(stocks)} rows to '{config.SHEET_TAB_DAILY}'")

    if not summary.empty:
        ws = get_or_create(config.SHEET_TAB_SUMMARY, list(summary.columns))
        ws.append_rows(summary.fillna("").values.tolist(), value_input_option="USER_ENTERED")
        print(f"[sheets] appended {len(summary)} rows to '{config.SHEET_TAB_SUMMARY}'")


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print digest to console, skip email + sheets")
    args = parser.parse_args()

    print(f"=== Market Pulse — {TODAY} ===")

    stocks = fetch_stock_data()
    summary = build_segment_summary(stocks)
    articles = fetch_news()
    insights = build_insights(stocks, articles)
    html = render_email_html(stocks, summary, articles, insights)

    # Always keep a local copy so no run is ever lost
    os.makedirs("output", exist_ok=True)
    stocks.to_csv(f"output/stocks_{TODAY}.csv", index=False)
    with open(f"output/digest_{TODAY}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[local] saved output/stocks_{TODAY}.csv and output/digest_{TODAY}.html")

    if args.dry_run:
        print("\n--- DRY RUN: segment summary ---")
        print(summary.to_string(index=False))
        print(f"\n{len(articles)} articles collected. Digest saved locally. Email + Sheets skipped.")
        return

    errors = []
    for step, fn in (("sheets", lambda: append_to_sheets(stocks, summary)),
                     ("email", lambda: send_email(html))):
        try:
            fn()
        except Exception:
            errors.append(step)
            print(f"[{step}] FAILED:\n{traceback.format_exc()}")

    if errors:
        print(f"Completed with errors in: {', '.join(errors)}")
        sys.exit(1)
    print("✅ Done.")


if __name__ == "__main__":
    main()
