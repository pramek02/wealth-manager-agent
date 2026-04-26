"""
Stock data module: fetches live prices via yfinance with mock fallback.
Analyst recommendations are mock-realistic data based on major bank consensus.
"""
import yfinance as yf
from datetime import datetime, date
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Fallback prices if yfinance is unavailable
FALLBACK_PRICES = {
    "AAPL": 196.45, "MSFT": 418.30, "NVDA": 875.20, "GOOGL": 167.80,
    "META": 548.60, "JNJ": 158.40, "UNH": 512.00, "JPM": 228.50,
    "BAC": 41.80, "GS": 488.20, "AMZN": 198.70, "TSLA": 248.30,
    "XOM": 113.40, "CVX": 158.20, "CAT": 352.10, "HON": 208.50,
    "PG": 163.80, "PFE": 26.40
}

# Mock analyst recommendations (realistic consensus as of early 2026)
ANALYST_RECOMMENDATIONS = {
    "AAPL": {
        "consensus": "Buy",
        "mean_rating": 2.1,
        "price_target": 230.00,
        "num_analysts": 42,
        "strong_buy": 18, "buy": 14, "hold": 8, "sell": 2, "strong_sell": 0,
        "recent_change": "Upgraded by Morgan Stanley to Overweight",
        "key_thesis": "Vision Pro ramp + services growth sustain premium multiple"
    },
    "MSFT": {
        "consensus": "Strong Buy",
        "mean_rating": 1.6,
        "price_target": 490.00,
        "num_analysts": 48,
        "strong_buy": 32, "buy": 12, "hold": 4, "sell": 0, "strong_sell": 0,
        "recent_change": "Price target raised by Goldman Sachs to $510",
        "key_thesis": "Azure AI workloads accelerating; Copilot monetization exceeding estimates"
    },
    "NVDA": {
        "consensus": "Strong Buy",
        "mean_rating": 1.4,
        "price_target": 1050.00,
        "num_analysts": 55,
        "strong_buy": 41, "buy": 10, "hold": 4, "sell": 0, "strong_sell": 0,
        "recent_change": "Maintained Strong Buy post Q4 earnings beat",
        "key_thesis": "Blackwell GPU demand far exceeds supply; data center capex super-cycle"
    },
    "GOOGL": {
        "consensus": "Buy",
        "mean_rating": 1.9,
        "price_target": 205.00,
        "num_analysts": 50,
        "strong_buy": 24, "buy": 18, "hold": 7, "sell": 1, "strong_sell": 0,
        "recent_change": "Upgraded by JPMorgan after AI Overviews monetization update",
        "key_thesis": "Search + YouTube + Cloud trifecta; Gemini integration gaining traction"
    },
    "META": {
        "consensus": "Strong Buy",
        "mean_rating": 1.5,
        "price_target": 650.00,
        "num_analysts": 52,
        "strong_buy": 36, "buy": 12, "hold": 4, "sell": 0, "strong_sell": 0,
        "recent_change": "Price target raised by BofA to $680 on Llama monetization",
        "key_thesis": "Ad efficiency + AI engagement; Ray-Ban smart glasses gaining momentum"
    },
    "JNJ": {
        "consensus": "Hold",
        "mean_rating": 2.8,
        "price_target": 168.00,
        "num_analysts": 22,
        "strong_buy": 4, "buy": 6, "hold": 9, "sell": 3, "strong_sell": 0,
        "recent_change": "Downgraded by Barclays citing talc liability overhang",
        "key_thesis": "MedTech innovation offset by persistent litigation; limited upside near-term"
    },
    "UNH": {
        "consensus": "Buy",
        "mean_rating": 1.8,
        "price_target": 590.00,
        "num_analysts": 28,
        "strong_buy": 14, "buy": 10, "hold": 4, "sell": 0, "strong_sell": 0,
        "recent_change": "Raised guidance after strong MLR improvement in Q1",
        "key_thesis": "Diversified revenue (Optum/UHC), aging demographics tailwind"
    },
    "JPM": {
        "consensus": "Strong Buy",
        "mean_rating": 1.7,
        "price_target": 265.00,
        "num_analysts": 30,
        "strong_buy": 18, "buy": 8, "hold": 4, "sell": 0, "strong_sell": 0,
        "recent_change": "Upgraded by Wells Fargo post stress test results",
        "key_thesis": "Best-in-class management, NII resilience, buybacks accelerating"
    },
    "BAC": {
        "consensus": "Buy",
        "mean_rating": 2.0,
        "price_target": 50.00,
        "num_analysts": 28,
        "strong_buy": 12, "buy": 10, "hold": 6, "sell": 0, "strong_sell": 0,
        "recent_change": "Price target raised to $52 by Deutsche Bank",
        "key_thesis": "Rate-sensitive balance sheet to benefit from rate normalization; cost cuts"
    },
    "GS": {
        "consensus": "Buy",
        "mean_rating": 1.9,
        "price_target": 545.00,
        "num_analysts": 24,
        "strong_buy": 12, "buy": 8, "hold": 4, "sell": 0, "strong_sell": 0,
        "recent_change": "Raised estimates after record IB revenue quarter",
        "key_thesis": "M&A cycle recovery, trading excellence, asset management growth"
    },
    "AMZN": {
        "consensus": "Strong Buy",
        "mean_rating": 1.5,
        "price_target": 245.00,
        "num_analysts": 55,
        "strong_buy": 38, "buy": 14, "hold": 3, "sell": 0, "strong_sell": 0,
        "recent_change": "Price target raised by Citi to $260 on AWS AI momentum",
        "key_thesis": "AWS margin expansion, advertising scale, logistics profitability"
    },
    "TSLA": {
        "consensus": "Hold",
        "mean_rating": 2.9,
        "price_target": 265.00,
        "num_analysts": 40,
        "strong_buy": 8, "buy": 10, "hold": 14, "sell": 6, "strong_sell": 2,
        "recent_change": "Downgraded by RBC citing competition from Chinese EVs",
        "key_thesis": "FSD/Robotaxi optionality vs. near-term margin pressure from price cuts"
    },
    "XOM": {
        "consensus": "Buy",
        "mean_rating": 2.0,
        "price_target": 128.00,
        "num_analysts": 25,
        "strong_buy": 10, "buy": 10, "hold": 5, "sell": 0, "strong_sell": 0,
        "recent_change": "Upgraded by Scotiabank on Pioneer synergy realization",
        "key_thesis": "Pioneer acquisition synergies, Guyana ramp, disciplined capex"
    },
    "CVX": {
        "consensus": "Hold",
        "mean_rating": 2.6,
        "price_target": 165.00,
        "num_analysts": 24,
        "strong_buy": 6, "buy": 8, "hold": 8, "sell": 2, "strong_sell": 0,
        "recent_change": "Hess deal regulatory uncertainty weighing on shares",
        "key_thesis": "Hess acquisition risks; Permian growth but execution dependent"
    },
    "CAT": {
        "consensus": "Buy",
        "mean_rating": 2.1,
        "price_target": 395.00,
        "num_analysts": 22,
        "strong_buy": 10, "buy": 8, "hold": 4, "sell": 0, "strong_sell": 0,
        "recent_change": "Maintained Buy; infrastructure spending visibility strong",
        "key_thesis": "Infrastructure Act spending cycle, mining capex recovery, pricing power"
    },
    "HON": {
        "consensus": "Hold",
        "mean_rating": 2.7,
        "price_target": 215.00,
        "num_analysts": 20,
        "strong_buy": 4, "buy": 6, "hold": 8, "sell": 2, "strong_sell": 0,
        "recent_change": "Elliott Management activist position announced",
        "key_thesis": "Portfolio transformation needed; sum-of-parts breakup value vs. execution risk"
    },
    "PG": {
        "consensus": "Buy",
        "mean_rating": 2.2,
        "price_target": 180.00,
        "num_analysts": 22,
        "strong_buy": 8, "buy": 8, "hold": 6, "sell": 0, "strong_sell": 0,
        "recent_change": "Maintained Buy; volume recovery in emerging markets",
        "key_thesis": "Pricing normalization, volume recovery; defensive dividend grower"
    },
    "PFE": {
        "consensus": "Hold",
        "mean_rating": 3.0,
        "price_target": 30.00,
        "num_analysts": 25,
        "strong_buy": 3, "buy": 5, "hold": 10, "sell": 6, "strong_sell": 1,
        "recent_change": "Downgraded by Morgan Stanley citing pipeline concerns",
        "key_thesis": "COVID revenue cliff, pipeline needs rebuild; deep value but uncertain timeline"
    },
    # Stocks available to buy (not currently held)
    "LLY": {
        "consensus": "Strong Buy",
        "mean_rating": 1.4,
        "price_target": 1050.00,
        "num_analysts": 30,
        "strong_buy": 22, "buy": 6, "hold": 2, "sell": 0, "strong_sell": 0,
        "recent_change": "Raised to Strong Buy by multiple analysts post-Zepbound data",
        "key_thesis": "Obesity/diabetes drug leadership; pipeline optionality; secular demand"
    },
    "ABBV": {
        "consensus": "Buy",
        "mean_rating": 1.9,
        "price_target": 205.00,
        "num_analysts": 24,
        "strong_buy": 12, "buy": 8, "hold": 4, "sell": 0, "strong_sell": 0,
        "recent_change": "Price target raised after Skyrizi/Rinvoq momentum",
        "key_thesis": "Humira cliff navigated; immunology franchise growth above estimates"
    },
    "V": {
        "consensus": "Strong Buy",
        "mean_rating": 1.6,
        "price_target": 330.00,
        "num_analysts": 35,
        "strong_buy": 22, "buy": 10, "hold": 3, "sell": 0, "strong_sell": 0,
        "recent_change": "Raised to Strong Buy by Morgan Stanley",
        "key_thesis": "Cross-border volume recovery, value-added services, pristine business model"
    },
    "NEE": {
        "consensus": "Buy",
        "mean_rating": 2.0,
        "price_target": 82.00,
        "num_analysts": 18,
        "strong_buy": 8, "buy": 7, "hold": 3, "sell": 0, "strong_sell": 0,
        "recent_change": "Upgraded as data center power demand secures long-term contracts",
        "key_thesis": "AI data center power demand; clean energy transition beneficiary"
    },
    "LIN": {
        "consensus": "Buy",
        "mean_rating": 1.9,
        "price_target": 480.00,
        "num_analysts": 20,
        "strong_buy": 10, "buy": 8, "hold": 2, "sell": 0, "strong_sell": 0,
        "recent_change": "Maintained Buy; hydrogen economy positioning",
        "key_thesis": "Industrial gases pricing power, clean hydrogen opportunity"
    }
}

# Sector to stocks mapping (for screening)
SECTOR_UNIVERSE = {
    "Technology": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMD", "ORCL", "CRM", "ADBE"],
    "Healthcare": ["JNJ", "UNH", "LLY", "ABBV", "PFE", "MRK", "TMO", "ABT"],
    "Financials": ["JPM", "BAC", "GS", "MS", "V", "MA", "BRK-B", "C"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "NKE", "MCD", "SBUX", "TJX", "LOW"],
    "Consumer Staples": ["PG", "KO", "PEP", "WMT", "COST", "MDLZ", "CL", "EL"],
    "Energy": ["XOM", "CVX", "SLB", "EOG", "COP", "PSX", "VLO", "OXY"],
    "Industrials": ["CAT", "HON", "GE", "RTX", "UPS", "DE", "MMM", "FDX"],
    "Communication Services": ["META", "GOOGL", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS"],
    "Materials": ["LIN", "APD", "SHW", "FCX", "NEM", "DD", "PPG", "ECL"],
    "Utilities": ["NEE", "DUK", "SO", "D", "EXC", "AEP", "PCG", "SRE"]
}


def get_current_price(symbol: str) -> float:
    """Fetch current price via yfinance with fallback."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        price = info.last_price
        if price and price > 0:
            return round(float(price), 2)
    except Exception as e:
        logger.warning(f"yfinance failed for {symbol}: {e}")
    return FALLBACK_PRICES.get(symbol, 100.0)


def get_batch_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch prices for multiple symbols efficiently."""
    prices = {}
    try:
        tickers = yf.download(
            " ".join(symbols),
            period="1d",
            auto_adjust=True,
            progress=False,
            threads=True
        )
        if not tickers.empty and "Close" in tickers.columns:
            for sym in symbols:
                try:
                    if sym in tickers["Close"].columns:
                        price = float(tickers["Close"][sym].dropna().iloc[-1])
                        prices[sym] = round(price, 2)
                    else:
                        prices[sym] = FALLBACK_PRICES.get(sym, 100.0)
                except Exception:
                    prices[sym] = FALLBACK_PRICES.get(sym, 100.0)
        else:
            raise ValueError("Empty price data")
    except Exception as e:
        logger.warning(f"Batch price fetch failed: {e}. Using fallbacks.")
        for sym in symbols:
            prices[sym] = FALLBACK_PRICES.get(sym, 100.0)
    return prices


def get_analyst_data(symbol: str) -> dict:
    """Return analyst recommendation data for a symbol."""
    return ANALYST_RECOMMENDATIONS.get(symbol, {
        "consensus": "Hold",
        "mean_rating": 3.0,
        "price_target": None,
        "num_analysts": 0,
        "strong_buy": 0, "buy": 0, "hold": 1, "sell": 0, "strong_sell": 0,
        "recent_change": "No recent changes",
        "key_thesis": "No analyst coverage available"
    })


def get_sector_candidates(sector: str, min_rating: str = "Buy") -> list[dict]:
    """Find highly-rated stocks in a sector that we could buy."""
    rating_threshold = {"Strong Buy": 1.5, "Buy": 2.5, "Hold": 3.5}.get(min_rating, 2.5)
    candidates = []
    for sym in SECTOR_UNIVERSE.get(sector, []):
        rec = get_analyst_data(sym)
        if rec.get("mean_rating", 5) <= rating_threshold:
            candidates.append({
                "symbol": sym,
                "consensus": rec["consensus"],
                "mean_rating": rec["mean_rating"],
                "price_target": rec.get("price_target"),
                "num_analysts": rec.get("num_analysts", 0),
                "key_thesis": rec.get("key_thesis", "")
            })
    return sorted(candidates, key=lambda x: x["mean_rating"])
