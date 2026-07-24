"""
Market Pulse — configuration
Edit this file to customize tickers, news feeds, keywords, and delivery settings.
Secrets (email password, sheet ID) live in the .env file, not here.
"""

# ---------------------------------------------------------------------------
# TECH SUPPLY CHAIN UNIVERSE
# Organized by layer so the digest gives you a big-picture view of where
# demand is flowing (upstream equipment -> chips -> infrastructure -> end products).
# Non-US tickers use Yahoo Finance suffixes: .KS (Korea), .T (Tokyo), .TW (Taiwan),
# .AS (Amsterdam), .DE (Germany), .HK (Hong Kong)
# ---------------------------------------------------------------------------
SUPPLY_CHAIN = {
    "EDA & Chip IP": [
        "SNPS",      # Synopsys
        "CDNS",      # Cadence
        "ARM",       # Arm Holdings
    ],
    "Semiconductor Equipment (upstream)": [
        "ASML",      # ASML (litho, NL)
        "AMAT",      # Applied Materials
        "LRCX",      # Lam Research
        "KLAC",      # KLA
        "8035.T",    # Tokyo Electron (Japan)
        "6857.T",    # Advantest (Japan, test equipment)
    ],
    "Foundry & Manufacturing": [
        "TSM",       # TSMC (ADR)
        "2330.TW",   # TSMC (Taiwan listing)
        "UMC",       # United Microelectronics
        "GFS",       # GlobalFoundries
        "INTC",      # Intel (IDM + foundry)
    ],
    "Memory & Storage": [
        "MU",        # Micron
        "005930.KS", # Samsung Electronics (Korea)
        "000660.KS", # SK Hynix (Korea)
        "WDC",       # Western Digital
        "STX",       # Seagate
    ],
    "Chip Designers (fabless)": [
        "NVDA",      # NVIDIA
        "AMD",       # AMD
        "QCOM",      # Qualcomm
        "AVGO",      # Broadcom
        "MRVL",      # Marvell
        "MediaTek",  # placeholder — real ticker below
        "2454.TW",   # MediaTek (Taiwan)
    ],
    "Networking & Data Center Hardware": [
        "ANET",      # Arista Networks
        "CSCO",      # Cisco
        "SMCI",      # Super Micro
        "DELL",      # Dell (servers)
        "HPE",       # HPE
        "VRT",       # Vertiv (power/cooling)
    ],
    "Cloud & Hyperscalers (demand side)": [
        "MSFT", "GOOGL", "AMZN", "META", "ORCL",
        "BABA",      # Alibaba Cloud (China)
    ],
    "Devices & Consumer OEM": [
        "AAPL",
        "2317.TW",   # Foxconn / Hon Hai (assembly, Taiwan)
        "6758.T",    # Sony (Japan)
        "1810.HK",   # Xiaomi (HK)
    ],
    "Software & AI Platforms": [
        "CRM", "NOW", "PLTR", "SAP",  # SAP (Germany, US ADR)
        "SNOW",
    ],
    "Distribution & Materials": [
        "ARW",       # Arrow Electronics (distributor)
        "AVT",       # Avnet (distributor)
        "SHIN-ETSU", # placeholder — real ticker below
        "4063.T",    # Shin-Etsu Chemical (silicon wafers, Japan)
        "LIN",       # Linde (industrial gases)
    ],
}

# Remove placeholder comment entries automatically
for _seg, _ticks in SUPPLY_CHAIN.items():
    SUPPLY_CHAIN[_seg] = [t for t in _ticks if t not in ("MediaTek", "SHIN-ETSU")]

# ---------------------------------------------------------------------------
# NEWS FEEDS (RSS — reliable, no scraping needed)
# Google News query feeds let you track any topic across many trusted outlets.
# ---------------------------------------------------------------------------
NEWS_FEEDS = {
    "CNBC Technology": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "Google News: Semiconductors": "https://news.google.com/rss/search?q=semiconductor%20supply%20chain&hl=en-US&gl=US&ceid=US:en",
    "Google News: AI Chips": "https://news.google.com/rss/search?q=AI%20chips%20demand&hl=en-US&gl=US&ceid=US:en",
    "Google News: Tech Earnings": "https://news.google.com/rss/search?q=tech%20earnings%20guidance&hl=en-US&gl=US&ceid=US:en",
    "Google News: Chip Export Controls": "https://news.google.com/rss/search?q=chip%20export%20controls%20tariffs&hl=en-US&gl=US&ceid=US:en",
}

# Only include articles published within this window (hours)
NEWS_LOOKBACK_HOURS = 24
MAX_ARTICLES_PER_FEED = 8

# Keywords tracked across headlines to surface what the market is talking about
TREND_KEYWORDS = [
    "AI", "artificial intelligence", "GPU", "data center", "datacenter",
    "capex", "earnings", "guidance", "tariff", "export control",
    "shortage", "inventory", "demand", "capacity", "foundry",
    "HBM", "memory", "cloud", "layoff", "acquisition", "antitrust",
    "China", "Taiwan", "subsidy", "CHIPS Act",
]

# ---------------------------------------------------------------------------
# ANALYSIS SETTINGS
# ---------------------------------------------------------------------------
HISTORY_DAYS = 45          # trading history pulled per ticker
VOLUME_SPIKE_RATIO = 1.75  # flag if today's volume > 1.75x its 20-day average
BIG_MOVE_PCT = 3.0         # flag single-day moves bigger than this

# ---------------------------------------------------------------------------
# GOOGLE SHEETS
# ---------------------------------------------------------------------------
SHEET_TAB_DAILY = "daily_log"          # one row per ticker per day
SHEET_TAB_SUMMARY = "segment_summary"  # one row per segment per day

# ---------------------------------------------------------------------------
# EMAIL
# ---------------------------------------------------------------------------
EMAIL_SUBJECT_PREFIX = "📊 Tech Supply Chain Pulse"
