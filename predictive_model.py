"""
Market Pulse — predictive model
Reads the daily output/stocks_*.csv history market_pulse.py has been writing all
month, fits a pooled logistic-regression momentum model per supply-chain segment
(numpy only, no new dependency), and writes:
  - output/predictions_<latest-date>.csv   per-segment forecast + backtest stats
  - output/monthly_forecast_<YYYY-MM>.md   narrative summary

Directional signal for research, not trading/investment advice — same caveat
market_pulse.py already carries for its same-day implications.
"""
from __future__ import annotations

import glob
import mimetypes
import os

import numpy as np
import pandas as pd

import config

OUTPUT_DIR = "output"
FEATURES = ["avg_1d", "avg_5d", "avg_20d", "avg_vol"]


# ===========================================================================
# 1. LOAD + AGGREGATE (mirrors market_pulse.build_segment_summary, per day)
# ===========================================================================
def load_history() -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "stocks_*.csv")))
    if not files:
        raise SystemExit("No output/stocks_*.csv files found — run market_pulse.py first.")
    stocks = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    stocks["date"] = pd.to_datetime(stocks["date"])
    return stocks.sort_values("date")


def daily_segment_summary(stocks: pd.DataFrame) -> pd.DataFrame:
    return (
        stocks.groupby(["date", "segment"])
        .agg(
            avg_1d=("chg_1d_pct", "mean"),
            avg_5d=("chg_5d_pct", "mean"),
            avg_20d=("chg_20d_pct", "mean"),
            avg_vol=("volume_vs_20d_avg", "mean"),
            n_tickers=("ticker", "count"),
        )
        .reset_index()
        .sort_values(["segment", "date"])
    )


# ===========================================================================
# 2. TRAINING FRAME — walk-forward: day t's features predict day t+1's direction
# ===========================================================================
def build_training_frame(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for seg, g in summary.groupby("segment"):
        g = g.sort_values("date").reset_index(drop=True)
        for i in range(len(g) - 1):
            today, tomorrow = g.iloc[i], g.iloc[i + 1]
            rows.append({
                "segment": seg,
                "date": today["date"],
                **{f: today[f] for f in FEATURES},
                "target": int(tomorrow["avg_1d"] > 0),
            })
    return pd.DataFrame(rows)


# ===========================================================================
# 3. LOGISTIC REGRESSION — numpy only, ridge-regularized gradient descent
# ===========================================================================
def standardize(X, mean=None, std=None):
    if mean is None:
        mean, std = X.mean(axis=0), X.std(axis=0)
        std = np.where(std == 0, 1.0, std)
    return (X - mean) / std, mean, std


def train_logistic(X, y, l2=0.05, lr=0.3, iters=3000):
    n, d = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(d + 1)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(Xb @ w)))
        grad = Xb.T @ (p - y) / n
        grad[1:] += l2 * w[1:] / n  # skip intercept
        w -= lr * grad
    return w


def predict_proba(X, w):
    Xb = np.hstack([np.ones((X.shape[0], 1)), X])
    return 1 / (1 + np.exp(-(Xb @ w)))


def backtest(train_df: pd.DataFrame, holdout_frac=0.2):
    """Chronological split (not random) — the honest way to test a time series
    model. Reports accuracy against the always-predict-majority-class baseline
    so the model's edge (if any) is visible, not just its raw accuracy."""
    dates = sorted(train_df["date"].unique())
    split_idx = max(1, int(len(dates) * (1 - holdout_frac)))
    cutoff = dates[split_idx]

    train = train_df[train_df["date"] < cutoff]
    test = train_df[train_df["date"] >= cutoff]
    if train.empty or test.empty:
        return None, None, None

    Xtr, mean, std = standardize(train[FEATURES].to_numpy(float))
    ytr = train["target"].to_numpy(float)
    w = train_logistic(Xtr, ytr)

    Xte, _, _ = standardize(test[FEATURES].to_numpy(float), mean, std)
    yte = test["target"].to_numpy(float)
    pred = (predict_proba(Xte, w) >= 0.5).astype(int)

    acc = float((pred == yte).mean())
    baseline = float(max(yte.mean(), 1 - yte.mean()))
    return acc, baseline, len(test)


# ===========================================================================
# 4. FORECAST — fit on all data, predict from the latest available day
# ===========================================================================
def forecast_segments(summary: pd.DataFrame, train_df: pd.DataFrame) -> pd.DataFrame:
    X_all, mean, std = standardize(train_df[FEATURES].to_numpy(float))
    y_all = train_df["target"].to_numpy(float)
    w = train_logistic(X_all, y_all)

    latest_date = summary["date"].max()
    latest = summary[summary["date"] == latest_date].copy()
    Xf, _, _ = standardize(latest[FEATURES].to_numpy(float), mean, std)
    latest["prob_up"] = predict_proba(Xf, w)

    def label(p):
        if p >= 0.60:
            return "Up-leaning"
        if p <= 0.40:
            return "Down-leaning"
        return "Flat / no edge"

    latest["forecast"] = latest["prob_up"].apply(label)
    # avg_20d on the latest day IS the segment's trailing ~month return —
    # reuse it directly instead of recomputing a cumulative index.
    latest = latest.rename(columns={"avg_20d": "month_to_date_pct"})
    return latest[["segment", "month_to_date_pct", "avg_vol", "prob_up", "forecast"]].sort_values(
        "prob_up", ascending=False
    )


# ===========================================================================
# 5. NARRATIVE
# ===========================================================================
def reading_it_bullets(forecast: pd.DataFrame) -> list[str]:
    """Rule-based synthesis bullets — deterministic, not AI-written commentary.
    Shared by the markdown narrative and the HTML report so there's one source
    of truth for "what the numbers mean" each month."""
    bullets = []

    up = forecast[forecast["forecast"] == "Up-leaning"]["segment"].tolist()
    down = forecast[forecast["forecast"] == "Down-leaning"]["segment"].tolist()
    if up:
        bullets.append(f"Momentum + volume currently favor continuation in: {', '.join(up)}.")
    if down:
        bullets.append(f"Momentum + volume currently lean lower in: {', '.join(down)}.")
    if not up and not down:
        bullets.append("No segment clears the model's confidence threshold — a mixed, directionless month.")

    upstream = forecast[forecast["segment"] == "Semiconductor Equipment (upstream)"]
    downstream = forecast[forecast["segment"] == "Cloud & Hyperscalers (demand side)"]
    if not upstream.empty and not downstream.empty:
        u, d = upstream.iloc[0], downstream.iloc[0]
        if u["forecast"] == d["forecast"] and u["forecast"] != "Flat / no edge":
            bullets.append(
                f"Upstream equipment and downstream cloud demand both lean the same "
                f"direction ({u['forecast']}) — when supply and demand signals agree "
                "end-to-end it's a stronger read than either alone."
            )
        elif {u["forecast"], d["forecast"]} == {"Up-leaning", "Down-leaning"}:
            bullets.append(
                "Upstream equipment and downstream cloud demand are pulling in opposite "
                "directions — worth watching for an inventory/capex mismatch working "
                "through the chain."
            )

    biggest = forecast.loc[forecast["month_to_date_pct"].abs().idxmax()]
    if abs(biggest["month_to_date_pct"]) >= 10 and biggest["forecast"] == "Flat / no edge":
        possessive = biggest["segment"] + ("'" if biggest["segment"].endswith("s") else "'s")
        bullets.append(
            f"{possessive} {biggest['month_to_date_pct']:+.1f}% month-to-date move is the "
            f"largest in the dataset, yet its next-session probability sits at just "
            f"{biggest['prob_up']:.0%} (flat) — a large trailing move with a cooling near-term "
            "signal, consistent with a segment that has already made most of its move for the period."
        )

    worst = forecast.loc[forecast["month_to_date_pct"].idxmin()]
    if worst["forecast"] == "Up-leaning" and worst["month_to_date_pct"] < 0:
        bullets.append(
            f"{worst['segment']} had the weakest month ({worst['month_to_date_pct']:+.1f}%) but the "
            f"model's strongest lean toward a bounce ({worst['prob_up']:.0%} up) — a mean-reversion "
            "read: the segment furthest behind is where recent volume and short-term momentum "
            "currently point hardest toward a recovery."
        )

    return bullets[:5]


def build_narrative(forecast: pd.DataFrame, acc, baseline, n_test, month_label: str) -> str:
    lines = [f"# Supply Chain Forecast — {month_label}", ""]

    if acc is not None:
        lines.append(
            f"**Backtest:** {acc:.0%} directional accuracy on the most recent "
            f"{n_test} held-out segment-days, vs. a {baseline:.0%} always-predict-majority "
            "baseline. Trained on ~1 month of daily snapshots pooled across 10 segments — "
            "small sample, treat probabilities as a directional lean, not a precise forecast."
        )
    lines.append("")

    best = forecast.sort_values("month_to_date_pct", ascending=False).iloc[0]
    worst = forecast.sort_values("month_to_date_pct", ascending=True).iloc[0]
    lines.append(
        f"**Month so far:** {best['segment']} led ({best['month_to_date_pct']:+.1f}%), "
        f"{worst['segment']} lagged ({worst['month_to_date_pct']:+.1f}%)."
    )
    lines.append("")

    lines.append("## Per-segment forecast")
    lines.append("")
    lines.append("| Segment | Month-to-date | Vol vs 20d avg | P(next move up) | Lean |")
    lines.append("|---|---|---|---|---|")
    for _, r in forecast.iterrows():
        lines.append(
            f"| {r['segment']} | {r['month_to_date_pct']:+.1f}% | {r['avg_vol']:.2f}x | "
            f"{r['prob_up']:.0%} | {r['forecast']} |"
        )
    lines.append("")

    lines.append("## Reading it")
    lines.append("")
    for bullet in reading_it_bullets(forecast):
        lines.append(f"- {bullet}")

    lines.append("")
    lines.append(
        "_Directional research signal derived from price/volume momentum only — not "
        "trading or investment advice._"
    )
    return "\n".join(lines)


# ===========================================================================
# 6. GOOGLE DRIVE — same service account as append_to_sheets(), scoped down
# ===========================================================================
def upload_to_drive(file_path: str, drive_filename: str | None = None) -> str | None:
    """Uploads a file to Drive with the same GOOGLE_SERVICE_ACCOUNT_JSON used for
    Sheets (its Cloud project already has the Drive API enabled per README setup).
    Uses its own narrowly-scoped credentials object (drive.file — only files this
    app creates) rather than gspread's broader drive scope. Optionally files it
    under GOOGLE_DRIVE_FOLDER_ID, and always shares it with EMAIL_SENDER (the
    owner's own account) so it's actually visible in their Drive, not just the
    service account's own hidden space."""
    creds_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    share_with = os.getenv("EMAIL_SENDER")

    if not os.path.exists(creds_path):
        print(f"[drive] credentials file not found at {creds_path} — skipping")
        return None

    from google.auth.transport.requests import Request
    from google.oauth2.service_account import Credentials
    import requests

    creds = Credentials.from_service_account_file(
        creds_path, scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    creds.refresh(Request())

    drive_filename = drive_filename or os.path.basename(file_path)
    mime_type = mimetypes.guess_type(drive_filename)[0] or "application/octet-stream"
    metadata = {"name": drive_filename}
    if folder_id:
        metadata["parents"] = [folder_id]

    # Two requests, not one multipart/form-data POST: Drive's multipart upload
    # endpoint actually expects multipart/related (RFC 2387), which `requests`'
    # `files=` param does not produce — that silently drops the metadata
    # (parents included) and the file lands in the service account's own
    # quota-less space instead of the shared folder. Create-then-patch sidesteps
    # the encoding entirely: metadata as plain JSON, content as a plain PATCH body.
    create = requests.post(
        "https://www.googleapis.com/drive/v3/files?fields=id",
        headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
        json=metadata,
        timeout=30,
    )
    if not create.ok:
        print(f"[drive] create failed for {drive_filename}: {create.status_code} {create.text[:300]}")
        return None
    file_id = create.json()["id"]

    with open(file_path, "rb") as fh:
        resp = requests.patch(
            f"https://www.googleapis.com/upload/drive/v3/files/{file_id}"
            "?uploadType=media&fields=id,webViewLink",
            headers={"Authorization": f"Bearer {creds.token}", "Content-Type": mime_type},
            data=fh,
            timeout=60,
        )
    if not resp.ok:
        print(f"[drive] content upload failed for {drive_filename}: {resp.status_code} {resp.text[:300]}")
        return None
    info = resp.json()

    if share_with:
        perm = requests.post(
            f"https://www.googleapis.com/drive/v3/files/{info['id']}/permissions"
            "?sendNotificationEmail=false",
            headers={"Authorization": f"Bearer {creds.token}"},
            json={"type": "user", "role": "writer", "emailAddress": share_with},
            timeout=30,
        )
        if not perm.ok:
            print(f"[drive] uploaded but sharing with {share_with} failed: {perm.status_code} {perm.text[:200]}")

    print(f"[drive] uploaded {drive_filename} -> {info.get('webViewLink')}")
    return info.get("webViewLink")


# ===========================================================================
# MAIN
# ===========================================================================
def main(report_pdf: str | None = None, upload: bool = True):
    stocks = load_history()
    summary = daily_segment_summary(stocks)
    train_df = build_training_frame(summary)

    acc, baseline, n_test = backtest(train_df)
    forecast = forecast_segments(summary, train_df)

    latest_date = summary["date"].max()
    month_label = latest_date.strftime("%B %Y")
    date_tag = latest_date.strftime("%Y-%m-%d")

    csv_path = os.path.join(OUTPUT_DIR, f"predictions_{date_tag}.csv")
    forecast.round(3).to_csv(csv_path, index=False)
    narrative = build_narrative(forecast, acc, baseline, n_test, month_label)
    md_path = os.path.join(OUTPUT_DIR, f"monthly_forecast_{latest_date.strftime('%Y-%m')}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(narrative)

    print(f"[predictive_model] {len(summary['date'].unique())} days, "
          f"{summary['segment'].nunique()} segments loaded")
    if acc is not None:
        print(f"[predictive_model] backtest accuracy: {acc:.0%} (baseline {baseline:.0%}, n={n_test})")
    print(f"[predictive_model] wrote predictions_{date_tag}.csv and {os.path.basename(md_path)}")
    print()
    print(narrative)

    if upload:
        targets = [csv_path, md_path]
        if report_pdf:
            targets.append(report_pdf)
        attempted = os.path.exists(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json"))
        failed = sum(1 for t in targets if upload_to_drive(t) is None)
        if attempted and failed:
            # Credentials were present (not a plain "unconfigured" skip) but the
            # upload(s) still failed — exit nonzero so CI shows this run as
            # failed instead of a misleading green checkmark.
            raise SystemExit(f"[drive] {failed}/{len(targets)} upload(s) failed — see errors above")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--report-pdf", help="Path to a rendered PDF report to also upload to Drive")
    parser.add_argument("--no-drive", action="store_true", help="Skip the Google Drive upload step")
    args = parser.parse_args()
    main(report_pdf=args.report_pdf, upload=not args.no_drive)
