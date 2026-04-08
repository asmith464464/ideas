"""
Master universe for idea 004 -- historically significant cryptocurrencies.

A curated list of coins that were at any point in the top-100 by market cap,
including coins that subsequently collapsed (LUNA, FTT, CEL, etc.).

Survivorship bias is handled by data availability gating: at each rebalance
date, a coin is only included if it has non-NaN price AND Trends data at that
point.  Collapsed coins naturally fall out when their data goes to zero/NaN.
No point-in-time market cap API required.

Each entry:
  symbol      -- ticker used for CryptoCompare price fetch and Trends queries
  name        -- full name (used as primary Google Trends keyword)
  cc_symbol   -- CryptoCompare symbol (usually same as symbol)
  yf_ticker   -- Yahoo Finance ticker if available, else None
  notes       -- why this coin is included (optional context)
"""

UNIVERSE: list[dict] = [
    # --- Layer 1 blue chips ---
    {"symbol": "BTC",   "name": "Bitcoin",          "cc_symbol": "BTC",   "yf_ticker": "BTC-USD"},
    {"symbol": "ETH",   "name": "Ethereum",          "cc_symbol": "ETH",   "yf_ticker": "ETH-USD"},
    {"symbol": "BNB",   "name": "BNB",               "cc_symbol": "BNB",   "yf_ticker": "BNB-USD"},
    {"symbol": "SOL",   "name": "Solana",            "cc_symbol": "SOL",   "yf_ticker": "SOL-USD"},
    {"symbol": "ADA",   "name": "Cardano",           "cc_symbol": "ADA",   "yf_ticker": "ADA-USD"},
    {"symbol": "XRP",   "name": "XRP",               "cc_symbol": "XRP",   "yf_ticker": "XRP-USD"},
    {"symbol": "DOT",   "name": "Polkadot",          "cc_symbol": "DOT",   "yf_ticker": "DOT-USD"},
    {"symbol": "AVAX",  "name": "Avalanche",         "cc_symbol": "AVAX",  "yf_ticker": "AVAX-USD"},
    {"symbol": "MATIC", "name": "Polygon",           "cc_symbol": "MATIC", "yf_ticker": "MATIC-USD"},
    {"symbol": "ATOM",  "name": "Cosmos",            "cc_symbol": "ATOM",  "yf_ticker": "ATOM-USD"},
    {"symbol": "LTC",   "name": "Litecoin",          "cc_symbol": "LTC",   "yf_ticker": "LTC-USD"},
    {"symbol": "BCH",   "name": "Bitcoin Cash",      "cc_symbol": "BCH",   "yf_ticker": "BCH-USD"},
    {"symbol": "TRX",   "name": "TRON",              "cc_symbol": "TRX",   "yf_ticker": "TRX-USD"},
    {"symbol": "ETC",   "name": "Ethereum Classic",  "cc_symbol": "ETC",   "yf_ticker": "ETC-USD"},
    {"symbol": "XLM",   "name": "Stellar",           "cc_symbol": "XLM",   "yf_ticker": "XLM-USD"},
    {"symbol": "ALGO",  "name": "Algorand",          "cc_symbol": "ALGO",  "yf_ticker": "ALGO-USD"},
    {"symbol": "VET",   "name": "VeChain",           "cc_symbol": "VET",   "yf_ticker": "VET-USD"},
    {"symbol": "ICP",   "name": "Internet Computer", "cc_symbol": "ICP",   "yf_ticker": "ICP-USD"},
    {"symbol": "FIL",   "name": "Filecoin",          "cc_symbol": "FIL",   "yf_ticker": "FIL-USD"},
    {"symbol": "EOS",   "name": "EOS",               "cc_symbol": "EOS",   "yf_ticker": "EOS-USD"},
    {"symbol": "XTZ",   "name": "Tezos",             "cc_symbol": "XTZ",   "yf_ticker": "XTZ-USD"},
    {"symbol": "NEAR",  "name": "NEAR Protocol",     "cc_symbol": "NEAR",  "yf_ticker": "NEAR-USD"},
    {"symbol": "APT",   "name": "Aptos",             "cc_symbol": "APT",   "yf_ticker": "APT-USD"},
    {"symbol": "ARB",   "name": "Arbitrum",          "cc_symbol": "ARB",   "yf_ticker": "ARB-USD"},
    {"symbol": "OP",    "name": "Optimism",          "cc_symbol": "OP",    "yf_ticker": "OP-USD"},
    {"symbol": "SUI",   "name": "Sui",               "cc_symbol": "SUI",   "yf_ticker": "SUI-USD"},

    # --- DeFi ---
    {"symbol": "LINK",  "name": "Chainlink",         "cc_symbol": "LINK",  "yf_ticker": "LINK-USD"},
    {"symbol": "UNI",   "name": "Uniswap",           "cc_symbol": "UNI",   "yf_ticker": "UNI-USD"},
    {"symbol": "AAVE",  "name": "Aave",              "cc_symbol": "AAVE",  "yf_ticker": "AAVE-USD"},
    {"symbol": "MKR",   "name": "Maker",             "cc_symbol": "MKR",   "yf_ticker": "MKR-USD"},
    {"symbol": "CRV",   "name": "Curve",             "cc_symbol": "CRV",   "yf_ticker": "CRV-USD"},
    {"symbol": "COMP",  "name": "Compound",          "cc_symbol": "COMP",  "yf_ticker": "COMP-USD"},
    {"symbol": "SNX",   "name": "Synthetix",         "cc_symbol": "SNX",   "yf_ticker": "SNX-USD"},
    {"symbol": "YFI",   "name": "Yearn Finance",     "cc_symbol": "YFI",   "yf_ticker": "YFI-USD"},
    {"symbol": "SUSHI", "name": "SushiSwap",         "cc_symbol": "SUSHI", "yf_ticker": "SUSHI-USD"},
    {"symbol": "CAKE",  "name": "PancakeSwap",       "cc_symbol": "CAKE",  "yf_ticker": "CAKE-USD"},
    {"symbol": "INJ",   "name": "Injective",         "cc_symbol": "INJ",   "yf_ticker": "INJ-USD"},

    # --- Meme coins ---
    {"symbol": "DOGE",  "name": "Dogecoin",          "cc_symbol": "DOGE",  "yf_ticker": "DOGE-USD"},
    {"symbol": "SHIB",  "name": "Shiba Inu",         "cc_symbol": "SHIB",  "yf_ticker": "SHIB-USD"},
    {"symbol": "PEPE",  "name": "Pepe",              "cc_symbol": "PEPE",  "yf_ticker": "PEPE-USD"},

    # --- Layer 2 / scaling ---
    {"symbol": "THETA", "name": "Theta Network",     "cc_symbol": "THETA", "yf_ticker": "THETA-USD"},
    {"symbol": "MANA",  "name": "Decentraland",      "cc_symbol": "MANA",  "yf_ticker": "MANA-USD"},
    {"symbol": "SAND",  "name": "The Sandbox",       "cc_symbol": "SAND",  "yf_ticker": "SAND-USD"},
    {"symbol": "AXS",   "name": "Axie Infinity",     "cc_symbol": "AXS",   "yf_ticker": "AXS-USD"},

    # --- Exchange tokens ---
    {"symbol": "OKB",   "name": "OKB",               "cc_symbol": "OKB",   "yf_ticker": None},
    {"symbol": "HT",    "name": "Huobi Token",       "cc_symbol": "HT",    "yf_ticker": None},
    {"symbol": "KCS",   "name": "KuCoin Token",      "cc_symbol": "KCS",   "yf_ticker": None},

    # --- Historical: notable failures / crashes (survivorship bias fix) ---
    {"symbol": "LUNA",  "name": "Terra Luna",        "cc_symbol": "LUNA",  "yf_ticker": "LUNA-USD",
     "notes": "Collapsed May 2022. Was top-10 before collapse."},
    {"symbol": "LUNC",  "name": "Terra Classic",     "cc_symbol": "LUNC",  "yf_ticker": "LUNC-USD",
     "notes": "Post-collapse remnant of LUNA."},
    {"symbol": "FTT",   "name": "FTX Token",         "cc_symbol": "FTT",   "yf_ticker": "FTT-USD",
     "notes": "Collapsed Nov 2022 with FTX exchange. Was top-20."},
    {"symbol": "CEL",   "name": "Celsius",           "cc_symbol": "CEL",   "yf_ticker": None,
     "notes": "Collapsed Jun 2022 with Celsius Network bankruptcy."},
    {"symbol": "WAVES", "name": "Waves",             "cc_symbol": "WAVES", "yf_ticker": "WAVES-USD",
     "notes": "Was top-50; significant decline after 2022."},
    {"symbol": "DASH",  "name": "Dash",              "cc_symbol": "DASH",  "yf_ticker": "DASH-USD",
     "notes": "Was top-10 in 2018; gradually fell from relevance."},
    {"symbol": "ZEC",   "name": "Zcash",             "cc_symbol": "ZEC",   "yf_ticker": "ZEC-USD",
     "notes": "Privacy coin; was top-20; declined significantly."},
    {"symbol": "NEO",   "name": "NEO",               "cc_symbol": "NEO",   "yf_ticker": "NEO-USD",
     "notes": "Chinese Ethereum; was top-10 in 2017-18."},
    {"symbol": "ZIL",   "name": "Zilliqa",           "cc_symbol": "ZIL",   "yf_ticker": "ZIL-USD"},
    {"symbol": "BAT",   "name": "Basic Attention Token", "cc_symbol": "BAT", "yf_ticker": "BAT-USD"},
    {"symbol": "ONE",   "name": "Harmony",           "cc_symbol": "ONE",   "yf_ticker": "ONE-USD"},
    {"symbol": "IOTA",  "name": "IOTA",              "cc_symbol": "IOTA",  "yf_ticker": None},
]

# Convenience lookups
BY_SYMBOL: dict[str, dict] = {c["symbol"]: c for c in UNIVERSE}
SYMBOLS: list[str] = [c["symbol"] for c in UNIVERSE]

# ---------------------------------------------------------------------------
# Wikipedia article names for pageviews API.
# Key: symbol.  Value: exact English Wikipedia article title.
# Omit coins with no meaningful Wikipedia article — they'll be excluded from
# the Wikipedia-based signal and fall back to price-only ranking.
# ---------------------------------------------------------------------------

WIKI_ARTICLES: dict[str, str] = {
    "BTC":   "Bitcoin",
    "ETH":   "Ethereum",
    "BNB":   "Binance",                    # BNB page redirects; Binance article has the views
    "SOL":   "Solana",
    "ADA":   "Cardano",
    "XRP":   "XRP_Ledger",
    "DOT":   "Polkadot_(blockchain_platform)",
    "AVAX":  "Avalanche_(blockchain_platform)",
    "MATIC": "Polygon_(blockchain)",
    "ATOM":  "Cosmos_(blockchain)",
    "LTC":   "Litecoin",
    "BCH":   "Bitcoin_Cash",
    "TRX":   "Tron_(blockchain)",
    "ETC":   "Ethereum_Classic",
    "XLM":   "Stellar_(payment_network)",
    "ALGO":  "Algorand",
    "VET":   "VeChain",
    "ICP":   "Internet_Computer",
    "FIL":   "Filecoin",
    "EOS":   "EOS.IO",
    "XTZ":   "Tezos",
    "NEAR":  "NEAR_Protocol",
    "LINK":  "Chainlink_(blockchain)",
    "UNI":   "Uniswap",
    "MKR":   "MakerDAO",
    "DOGE":  "Dogecoin",
    "SHIB":  "Shiba_Inu_(cryptocurrency)",
    "MANA":  "Decentraland",
    "SAND":  "The_Sandbox_(video_game)",
    "AXS":   "Axie_Infinity",
    # Historical failures — key survivorship-bias test coins
    "LUNA":  "Terra_(blockchain)",
    "FTT":   "FTX",                        # FTX article captures the collapse peak
    "WAVES": "Waves_(blockchain)",
    "DASH":  "Dash_(cryptocurrency)",
    "ZEC":   "Zcash",
    "NEO":   "NEO_(blockchain)",
    "BAT":   "Basic_Attention_Token",
    "ZIL":   "Zilliqa",
}

# ---------------------------------------------------------------------------
# Google Trends keyword overrides
# Default keyword = coin name lowercased, which is ambiguous for some coins.
# These overrides use more specific search terms to reduce non-crypto noise.
# ---------------------------------------------------------------------------

TRENDS_KEYWORDS: dict[str, str] = {
    "BTC":   "bitcoin",
    "EOS":   "eos crypto",       # "eos" matches camera brand + skincare brand
    "SUI":   "sui blockchain",   # "sui" matches swimming brand + Japanese word
    "NEO":   "neo crypto",       # "neo" matches Matrix character + band
    "OP":    "optimism crypto",  # "optimism" is a common English word
    "COMP":  "compound finance", # "compound" is a common English word
    "CRV":   "curve finance",    # "curve" is a common English word
    "MKR":   "makerdao",         # "maker" is a common English word
    "CEL":   "celsius network",  # "celsius" primarily matches temperature scale
    "PEPE":  "pepe coin",        # "pepe" matches Pepe the Frog meme
    "OKB":   "okx token",        # "okb" is obscure; "okx" is the exchange name
    "ONE":   "harmony crypto",   # "harmony" is a common word; ONE is very short
    "BAT":   "basic attention token",  # "bat" matches the animal
}


def get_universe() -> list[dict]:
    """Return the full master universe list."""
    return UNIVERSE


def filter_available(
    symbols: list[str],
    prices,
    trends,
    date,
) -> list[str]:
    """
    Filter a symbol list to those with valid (non-NaN) price AND Trends data
    at or before `date`.  This gates survivorship bias: collapsed coins fall
    out naturally when their data goes to NaN/zero.
    """
    available = []
    for sym in symbols:
        has_price  = sym in prices.columns  and prices.loc[:date, sym].dropna().shape[0] > 0
        has_trends = sym in trends.columns  and trends.loc[:date, sym].dropna().shape[0] > 0
        if has_price and has_trends:
            available.append(sym)
    return available
