"""Fixed ILLUSTRATIVE mappings for what the engine does not hold.

The engine simulates broad asset classes (stocks, bonds, private credit) and, for a direct-indexed account, 100 anonymous stocks. It has no
company names, sectors, regions, fund names or a US / international split. Where the customer view shows any of these, it applies the
fixed weights below to the engine's own stock amounts. They are rounded approximations of the weights of broad published equity indexes
(a US large-cap index and a global all-country index) at an unspecified recent date, chosen once and never tuned. They are NOT engine
output, and the API marks every section that uses them (`illustrative`).
"""

from __future__ import annotations

# Share of stocks held in US companies; the rest is international. (A global all-country index is roughly this US-weighted.)
US_SHARE_OF_STOCKS = 0.65

# Sector weights of a broad equity portfolio (sum 1.0).
SECTORS: tuple[tuple[str, float], ...] = (
    ("Technology", 0.32),
    ("Financials", 0.14),
    ("Health care", 0.10),
    ("Consumer discretionary", 0.10),
    ("Communication services", 0.09),
    ("Industrials", 0.08),
    ("Consumer staples", 0.06),
    ("Energy", 0.03),
    ("Utilities", 0.03),
    ("Real estate", 0.02),
    ("Materials", 0.03),
)

# How the international part of stocks is spread over regions (sum 1.0); the US is `US_SHARE_OF_STOCKS`.
INTERNATIONAL_REGIONS: tuple[tuple[str, float], ...] = (
    ("Europe", 0.43),
    ("Japan", 0.14),
    ("Asia excluding Japan", 0.20),
    ("Other", 0.23),
)

# Largest companies of a US large-cap index, as a share of US stocks (only shown for a direct-indexed holding).
LARGEST_US_STOCKS: tuple[tuple[str, float], ...] = (
    ("Microsoft", 0.065),
    ("Nvidia", 0.065),
    ("Apple", 0.060),
    ("Amazon", 0.038),
    ("Alphabet", 0.035),
    ("Meta Platforms", 0.025),
    ("Broadcom", 0.022),
    ("Tesla", 0.018),
    ("Berkshire Hathaway", 0.016),
    ("JPMorgan Chase", 0.015),
)

FUND_NAMES = {
    "us_stocks": "US stock index fund",
    "intl_stocks": "International stock index fund",
    "bonds": "Bond index fund",
    "private_credit": "Private credit fund",
    "cash": "Cash",
}
DIRECT_INDEXING_NAME = "Direct-indexed US stocks"
