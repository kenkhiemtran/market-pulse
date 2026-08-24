# Supply Chain Forecast — August 2026

**Backtest:** 65% directional accuracy on the most recent 60 held-out segment-days, vs. a 57% always-predict-majority baseline. Trained on ~1 month of daily snapshots pooled across 10 segments — small sample, treat probabilities as a directional lean, not a precise forecast.

**Month so far:** Software & AI Platforms led (+33.0%), Distribution & Materials lagged (-4.9%).

## Per-segment forecast

| Segment | Month-to-date | Vol vs 20d avg | P(next move up) | Lean |
|---|---|---|---|---|
| Networking & Data Center Hardware | +5.5% | 0.68x | 71% | Up-leaning |
| Distribution & Materials | -4.9% | 0.82x | 68% | Up-leaning |
| Foundry & Manufacturing | -2.4% | 0.64x | 67% | Up-leaning |
| Semiconductor Equipment (upstream) | -3.1% | 0.63x | 65% | Up-leaning |
| Memory & Storage | -2.5% | 0.65x | 63% | Up-leaning |
| Devices & Consumer OEM | +2.2% | 0.68x | 61% | Up-leaning |
| EDA & Chip IP | -0.7% | 0.80x | 60% | Up-leaning |
| Software & AI Platforms | +33.0% | 0.67x | 58% | Flat / no edge |
| Chip Designers (fabless) | +1.7% | 0.80x | 57% | Flat / no edge |
| Cloud & Hyperscalers (demand side) | +12.0% | 1.11x | 53% | Flat / no edge |

## Reading it

- Momentum + volume currently favor continuation in: Networking & Data Center Hardware, Distribution & Materials, Foundry & Manufacturing, Semiconductor Equipment (upstream), Memory & Storage, Devices & Consumer OEM, EDA & Chip IP.
- Software & AI Platforms' +33.0% month-to-date move is the largest in the dataset, yet its next-session probability sits at just 58% (flat) — a large trailing move with a cooling near-term signal, consistent with a segment that has already made most of its move for the period.
- Distribution & Materials had the weakest month (-4.9%) but the model's strongest lean toward a bounce (68% up) — a mean-reversion read: the segment furthest behind is where recent volume and short-term momentum currently point hardest toward a recovery.

_Directional research signal derived from price/volume momentum only — not trading or investment advice._