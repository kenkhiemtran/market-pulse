"""
Market Pulse — HTML/PDF report renderer
Runs the same forecasting pipeline as predictive_model.py, renders it into the
designed report_assets/template.html (fonts cached locally, no network needed),
exports a PDF via headless Edge/Chrome, and copies the whole package into a
local folder — default ~/Downloads/Forecast Report/<YYYY-MM>/.

Standalone from predictive_model.py's own CSV/MD + Drive upload: this is the
polished, human-facing artifact. Run both for the full package (this script
calls predictive_model.main(upload=False) itself, so one run is enough).
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess

import predictive_model as pm

ASSETS_DIR = "report_assets"
DEFAULT_DEST = os.path.join(os.path.expanduser("~"), "Downloads", "Forecast Report")

BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

# A couple of segment names are long enough to want a shortened chart label —
# the full name still appears in the table and the bar's tooltip/aria-label.
SHORT_LABELS = {
    "Semiconductor Equipment (upstream)": ("Semiconductor Equipment", "upstream"),
    "Chip Designers (fabless)": ("Chip Designers", "fabless"),
    "Networking & Data Center Hardware": ("Networking & Data Center", "hardware"),
    "Cloud & Hyperscalers (demand side)": ("Cloud & Hyperscalers", "demand side"),
}


def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def build_forecast() -> dict:
    stocks = pm.load_history()
    summary = pm.daily_segment_summary(stocks)
    train_df = pm.build_training_frame(summary)
    acc, baseline, n_test = pm.backtest(train_df)
    forecast = pm.forecast_segments(summary, train_df)

    order = list(pm.config.SUPPLY_CHAIN.keys())
    present = [s for s in order if s in set(forecast["segment"])]
    ordered = forecast.set_index("segment").loc[present].reset_index()

    return {
        "summary": summary,
        "ordered": ordered,
        "acc": acc,
        "baseline": baseline,
        "n_test": n_test,
        "latest_date": summary["date"].max(),
    }


def _chart_row(seg_full: str, value: float) -> dict:
    seg, sub = SHORT_LABELS.get(seg_full, (seg_full, ""))
    return {"seg": seg, "sub": sub, "v": round(float(value), 1)}


def render_html(data: dict) -> str:
    ordered = data["ordered"]
    with open(os.path.join(ASSETS_DIR, "template.html"), "r", encoding="utf-8") as f:
        html = f.read()

    month_label = data["latest_date"].strftime("%B %Y")
    dates = data["summary"]["date"]
    date_window = f"{dates.min().strftime('%b %d')} \u2013 {dates.max().strftime('%b %d, %Y')}"

    best = ordered.loc[ordered["month_to_date_pct"].idxmax()]
    worst = ordered.loc[ordered["month_to_date_pct"].idxmin()]

    chart_data = {
        "mtd": [_chart_row(s, v) for s, v in zip(ordered["segment"], ordered["month_to_date_pct"])],
        "mtdDomain": max(1.0, float(ordered["month_to_date_pct"].abs().max())),
        "prob": [_chart_row(s, v) for s, v in zip(ordered["segment"], ordered["prob_up"] * 100)],
    }

    lean_class = {"Up-leaning": "up", "Down-leaning": "down", "Flat / no edge": "flat"}
    table_rows = "\n".join(
        f'        <tr><td class="seg">{r["segment"]}</td>'
        f'<td class="num">{r["month_to_date_pct"]:+.1f}%</td>'
        f'<td class="num">{r["avg_vol"]:.2f}x</td>'
        f'<td class="num">{r["prob_up"]*100:.1f}%</td>'
        f'<td><span class="lean-chip {lean_class.get(r["forecast"], "flat")}"><i></i>{r["forecast"]}</span></td></tr>'
        for _, r in ordered.iterrows()
    )
    narrative_items = "\n".join(f"      <li>{b}</li>" for b in pm.reading_it_bullets(ordered))

    replacements = {
        "{{MONTH_LABEL}}": month_label,
        "{{NUM_DAYS}}": str(data["summary"]["date"].nunique()),
        "{{DATE_WINDOW}}": date_window,
        "{{NUM_SEGMENTS}}": str(ordered["segment"].nunique()),
        "{{GENERATED_DATE}}": data["latest_date"].strftime("%b %d, %Y"),
        "{{BACKTEST_ACC}}": f"{data['acc']*100:.0f}" if data["acc"] is not None else "\u2014",
        "{{BACKTEST_BASELINE}}": f"{data['baseline']*100:.0f}" if data["baseline"] is not None else "\u2014",
        "{{TEST_N}}": str(data["n_test"]) if data["n_test"] is not None else "\u2014",
        "{{LEADER_PCT}}": f"{best['month_to_date_pct']:+.1f}",
        "{{LEADER_SEG}}": best["segment"],
        "{{LAGGARD_PCT}}": f"{worst['month_to_date_pct']:+.1f}",
        "{{LAGGARD_SEG}}": worst["segment"],
        "{{NARRATIVE_ITEMS}}": narrative_items,
        "{{TABLE_ROWS}}": table_rows,
        "{{CHART_DATA_JSON}}": json.dumps(chart_data),
        "{{FONT_BSD}}": _b64(os.path.join(ASSETS_DIR, "fonts", "BigShouldersDisplay.woff2")),
        "{{FONT_PLEXSANS}}": _b64(os.path.join(ASSETS_DIR, "fonts", "IBMPlexSans.woff2")),
        "{{FONT_PLEXMONO400}}": _b64(os.path.join(ASSETS_DIR, "fonts", "IBMPlexMono-Regular.woff2")),
        "{{FONT_PLEXMONO500}}": _b64(os.path.join(ASSETS_DIR, "fonts", "IBMPlexMono-Medium.woff2")),
    }
    for token, value in replacements.items():
        html = html.replace(token, value)
    return html


def find_browser() -> str | None:
    return next((p for p in BROWSER_CANDIDATES if os.path.exists(p)), None)


def export_pdf(html_path: str, pdf_path: str) -> bool:
    browser = find_browser()
    if not browser:
        print("[report] no Edge/Chrome install found — skipping PDF export")
        return False
    profile_dir = os.path.join(os.environ.get("TEMP", "."), "report-pdf-profile")
    # Headless Edge/Chrome silently produces no file when spawned directly from
    # a Python process running under Git Bash/MSYS2 (no real Win32 console in
    # that process tree) — invoking it through a native powershell.exe host
    # fixes that, and is also the more robust choice for an unattended
    # Task Scheduler run.
    ps_cmd = (
        f'& "{browser}" --headless=new --disable-gpu --no-sandbox '
        f'--user-data-dir="{profile_dir}" --print-to-pdf="{pdf_path}" '
        f'--no-pdf-header-footer "file:///{os.path.abspath(html_path)}"'
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        capture_output=True, text=True, timeout=60,
    )
    if not os.path.exists(pdf_path):
        print(f"[report] PDF export failed (exit {result.returncode}): {result.stderr[:300]}")
        return False
    return True


def main(dest_root: str | None = None) -> str:
    dest_root = dest_root or DEFAULT_DEST

    # Generates/refreshes output/predictions_*.csv and monthly_forecast_*.md —
    # skip their (currently broken, see monthly-forecast.yml) Drive upload.
    pm.main(upload=False)

    data = build_forecast()
    month_tag = data["latest_date"].strftime("%Y-%m")
    month_label = data["latest_date"].strftime("%B %Y")
    dest_dir = os.path.join(dest_root, month_tag)
    os.makedirs(dest_dir, exist_ok=True)

    base_name = f"Supply Chain Forecast - {month_label}"
    html_path = os.path.join(dest_dir, f"{base_name}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(data))
    print(f"[report] wrote {html_path}")

    pdf_path = os.path.join(dest_dir, f"{base_name}.pdf")
    if export_pdf(html_path, pdf_path):
        print(f"[report] wrote {pdf_path}")

    date_tag = data["latest_date"].strftime("%Y-%m-%d")
    for name in (f"predictions_{date_tag}.csv", f"monthly_forecast_{month_tag}.md"):
        src = os.path.join(pm.OUTPUT_DIR, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest_dir, name))

    print(f"[report] report package saved to {dest_dir}")
    return dest_dir


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", help="Local folder to save the report package into")
    args = parser.parse_args()
    main(dest_root=args.dest)
