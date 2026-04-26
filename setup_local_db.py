"""
Builds a local DuckDB database (data/stocks.db) that mirrors the MotherDuck ndl schema:
  - stocks       (ticker, name, sector, industry, scalemarketcap, exchange, ...)
  - prices       (ticker, close, marketcap, pb)
  - recommendations (ticker, recommendation)  ← P/B percentile, same methodology

Run once before starting the server:
    python3 setup_local_db.py
"""
import duckdb
import pandas as pd
import yfinance as yf
from pathlib import Path
import logging, time

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "stocks.db"

# Portfolio holdings + curated buy candidates per sector (universe for screening)
ALL_TICKERS = [
    # Portfolio holdings (49)
    "AAPL","ABBV","ABT","AMT","AMZN","AVGO","AXP","BAC","BRK-B","CAT",
    "COP","COST","CRM","CSCO","CVX","DUK","FCX","GE","GOOGL","HD",
    "IBM","JNJ","JPM","LIN","LLY","MA","MCD","META","MSFT","NEE",
    "NFLX","NVDA","ORCL","PG","PLD","RTX","SHW","SO","T","TJX",
    "TMUS","TSLA","UNH","UNP","V","WELL","WFC","WMT","XOM",
    # Buy candidates by sector (for screening underweight sectors)
    # Technology
    "AMD","ADBE","INTC","NOW","SNPS","KLAC","AMAT","TXN","QCOM","MU",
    # Financial Services
    "MS","C","BLK","SCHW","USB","PNC","TFC","COF","ICE","CME",
    # Healthcare
    "MRK","BMY","AMGN","GILD","VRTX","REGN","TMO","DHR","MDT","SYK",
    # Consumer Cyclical
    "NKE","SBUX","LOW","F","GM","ABNB","BKNG","MAR","YUM","DG",
    # Communication Services
    "DIS","CMCSA","VZ","NFLX","EA","WBD","PARA","SNAP","PINS","MTCH",
    # Industrials
    "HON","MMM","DE","ETN","EMR","PH","FDX","UPS","LMT","NOC",
    # Consumer Defensive
    "KO","PEP","MDLZ","KMB","CL","SJM","K","HRL","CPB","TSN",
    # Energy
    "SLB","EOG","OXY","DVN","MPC","PSX","VLO","HES","FANG","APA",
    # Real Estate
    "SPG","O","DLR","PSA","EQR","AVB","VTR","INVH","MPW","IRM",
    # Basic Materials
    "APD","ECL","NEM","FCX","NUE","CF","MOS","ALB","PPG","DD",
    # Utilities
    "DUK","AEP","EXC","XEL","WEC","ES","ETR","FE","PPL","AES",
]
# Deduplicate
ALL_TICKERS = list(dict.fromkeys(ALL_TICKERS))

# Manual sector/industry mapping for tickers yfinance might mis-classify
SECTOR_OVERRIDES = {
    "BRK-B": ("Financial Services", "Insurance - Diversified"),
    "GOOGL": ("Communication Services", "Internet Content & Information"),
    "META":  ("Communication Services", "Internet Content & Information"),
    "AMZN":  ("Consumer Cyclical", "Internet Retail"),
    "TSLA":  ("Consumer Cyclical", "Auto Manufacturers"),
    "NFLX":  ("Communication Services", "Entertainment"),
    "TMUS":  ("Communication Services", "Telecom Services"),
    "T":     ("Communication Services", "Telecom Services"),
}

# Sector normalization (yfinance uses slightly different names)
SECTOR_MAP = {
    "Technology": "Technology",
    "Financial Services": "Financial Services",
    "Healthcare": "Healthcare",
    "Consumer Cyclical": "Consumer Cyclical",
    "Communication Services": "Communication Services",
    "Industrials": "Industrials",
    "Consumer Defensive": "Consumer Defensive",
    "Energy": "Energy",
    "Real Estate": "Real Estate",
    "Basic Materials": "Basic Materials",
    "Utilities": "Utilities",
    # yfinance variants
    "Consumer Staples": "Consumer Defensive",
    "Consumer Discretionary": "Consumer Cyclical",
    "Financials": "Financial Services",
    "Materials": "Basic Materials",
}

def marketcap_scale(mc_usd: float) -> str:
    if mc_usd >= 200e9:   return "6 - Mega"
    if mc_usd >= 10e9:    return "5 - Large"
    if mc_usd >= 2e9:     return "4 - Mid"
    if mc_usd >= 300e6:   return "3 - Small"
    return "2 - Micro"

def pb_to_recommendation(pb: float, all_pbs: list[float]) -> str:
    """Same methodology as MotherDuck ndl: P/B percentile ranking."""
    if pd.isna(pb) or pb <= 0:
        return "Hold"
    sorted_pbs = sorted(p for p in all_pbs if not pd.isna(p) and p > 0)
    n = len(sorted_pbs)
    rank = sorted_pbs.index(min(sorted_pbs, key=lambda x: abs(x - pb)))
    pct = rank / n
    if pct < 0.10:   return "Strong Buy"
    if pct < 0.30:   return "Buy"
    if pct < 0.70:   return "Hold"
    return "Sell"


def build_db():
    log.info(f"Building local stock database with {len(ALL_TICKERS)} tickers…")
    DB_PATH.parent.mkdir(exist_ok=True)

    records = []
    batch_size = 20

    for i in range(0, len(ALL_TICKERS), batch_size):
        batch = ALL_TICKERS[i:i+batch_size]
        log.info(f"  Fetching {batch}…")
        for ticker in batch:
            try:
                t = yf.Ticker(ticker)
                info = t.info or {}

                # Price
                price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
                if not price:
                    try:
                        price = float(t.fast_info.last_price)
                    except Exception:
                        price = None

                # Market cap
                mc = info.get("marketCap")
                if not mc:
                    try:
                        mc = float(t.fast_info.market_cap)
                    except Exception:
                        mc = None

                # P/B
                pb = info.get("priceToBook")

                # Sector / Industry
                if ticker in SECTOR_OVERRIDES:
                    sector, industry = SECTOR_OVERRIDES[ticker]
                else:
                    raw_sector = info.get("sector", "")
                    sector = SECTOR_MAP.get(raw_sector, raw_sector or "Unknown")
                    industry = info.get("industry", "")

                name = info.get("longName") or info.get("shortName") or ticker
                exchange = info.get("exchange", "NASDAQ")

                mc_k = mc / 1000 if mc else None
                scale = marketcap_scale(mc) if mc else "4 - Mid"

                records.append({
                    "ticker": ticker,
                    "name": name[:80],
                    "sector": sector,
                    "industry": (industry or "")[:80],
                    "scalemarketcap": scale,
                    "exchange": exchange,
                    "price": round(float(price), 4) if price else None,
                    "marketcap": round(float(mc_k), 2) if mc_k else None,
                    "pb": round(float(pb), 4) if pb else None,
                })
            except Exception as e:
                log.warning(f"  Failed {ticker}: {e}")
                records.append({
                    "ticker": ticker, "name": ticker, "sector": "Unknown",
                    "industry": "", "scalemarketcap": "4 - Mid", "exchange": "NASDAQ",
                    "price": None, "marketcap": None, "pb": None,
                })
        time.sleep(0.5)

    df = pd.DataFrame(records)

    # Assign recommendations using P/B percentile
    all_pbs = df["pb"].dropna().tolist()
    df["recommendation"] = df["pb"].apply(
        lambda pb: pb_to_recommendation(pb, all_pbs) if pb else "Hold"
    )

    # Ensure correct dtypes before writing
    df["ticker"] = df["ticker"].astype(str)
    df["name"] = df["name"].astype(str)
    df["sector"] = df["sector"].astype(str)
    df["industry"] = df["industry"].astype(str)
    df["scalemarketcap"] = df["scalemarketcap"].astype(str)
    df["exchange"] = df["exchange"].astype(str)
    df["recommendation"] = df["recommendation"].astype(str)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["marketcap"] = pd.to_numeric(df["marketcap"], errors="coerce")
    df["pb"] = pd.to_numeric(df["pb"], errors="coerce")

    # Write to DuckDB using explicit inserts to avoid type inference issues
    conn = duckdb.connect(str(DB_PATH))
    conn.execute("DROP TABLE IF EXISTS stocks")
    conn.execute("DROP TABLE IF EXISTS prices")
    conn.execute("DROP TABLE IF EXISTS recommendations")

    conn.execute("""CREATE TABLE stocks (
        ticker VARCHAR, name VARCHAR, sector VARCHAR,
        industry VARCHAR, scalemarketcap VARCHAR, exchange VARCHAR
    )""")
    conn.execute("""CREATE TABLE prices (
        ticker VARCHAR, close DOUBLE, marketcap DOUBLE, pb DOUBLE
    )""")
    conn.execute("""CREATE TABLE recommendations (
        ticker VARCHAR, recommendation VARCHAR
    )""")

    for _, row in df.iterrows():
        t = str(row["ticker"])
        conn.execute("INSERT INTO stocks VALUES (?,?,?,?,?,?)", [
            t, str(row["name"]), str(row["sector"]),
            str(row["industry"]), str(row["scalemarketcap"]), str(row["exchange"])
        ])
        p = row["price"]
        if pd.notna(p):
            conn.execute("INSERT INTO prices VALUES (?,?,?,?)", [
                t,
                float(p),
                float(row["marketcap"]) if pd.notna(row["marketcap"]) else None,
                float(row["pb"]) if pd.notna(row["pb"]) else None,
            ])
        conn.execute("INSERT INTO recommendations VALUES (?,?)", [
            t, str(row["recommendation"])
        ])

    n = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
    log.info(f"✓ Database built: {n} stocks at {DB_PATH}")

    # Sample check
    sample = conn.execute("""
        SELECT s.ticker, s.sector, p.close, p.pb, r.recommendation
        FROM stocks s JOIN prices p ON s.ticker=p.ticker
        JOIN recommendations r ON s.ticker=r.ticker
        LIMIT 5
    """).fetchdf()
    log.info(f"\nSample:\n{sample.to_string()}")
    conn.close()


if __name__ == "__main__":
    build_db()
