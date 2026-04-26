"""
Database layer: tries MotherDuck first; falls back to local DuckDB (data/stocks.db).
Both expose the same schema: stocks / prices / recommendations.
"""
import os
import duckdb
import pandas as pd
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MOTHERDUCK_TOKEN = os.environ.get("MOTHERDUCK_TOKEN", "")
MOTHERDUCK_DB = "student_stocks"
LOCAL_DB = Path(__file__).parent / "data" / "stocks.db"


def _get_conn() -> tuple[duckdb.DuckDBPyConnection, str]:
    """Return (connection, source_label). Prefers MotherDuck student_stocks, falls back to local."""
    # Try MotherDuck
    try:
        conn = duckdb.connect(f"md:{MOTHERDUCK_DB}?motherduck_token={MOTHERDUCK_TOKEN}")
        # Verify tables exist
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name IN ('stocks','prices','recommendations')"
        ).fetchdf()
        if len(tables) == 3:
            return conn, "MotherDuck (student_stocks)"
        conn.close()
    except Exception as e:
        logger.debug(f"MotherDuck unavailable: {e}")

    # Fall back to local DB
    if LOCAL_DB.exists():
        return duckdb.connect(str(LOCAL_DB), read_only=True), "local"

    raise RuntimeError(
        "No stock database available. Run `python3 setup_local_db.py` to build the local DB."
    )


def run_sql(query: str) -> pd.DataFrame:
    """Execute a SQL query against whichever database is available."""
    conn, source = _get_conn()
    try:
        result = conn.execute(query).fetchdf()
        return result
    finally:
        conn.close()


def get_prices_and_ratings(tickers: list[str]) -> pd.DataFrame:
    """
    Fetch price, market cap, P/B, sector, industry, and recommendation
    for a list of tickers. Returns one row per ticker.
    """
    ticker_list = ", ".join(f"'{t}'" for t in tickers)
    query = f"""
        SELECT
            s.ticker,
            s.name,
            s.sector,
            s.industry,
            s.scalemarketcap,
            p.close       AS price,
            p.marketcap,
            p.pb,
            r.recommendation
        FROM stocks s
        JOIN prices p ON s.ticker = p.ticker
        JOIN recommendations r ON s.ticker = r.ticker
        WHERE s.ticker IN ({ticker_list})
    """
    return run_sql(query)


def get_sector_candidates(
    sector: str,
    ratings: list[str] = None,
    exclude_tickers: list[str] = None,
) -> pd.DataFrame:
    """
    Find Mega/Large-cap stocks in a sector with given ratings.
    Excludes tobacco (MO, PM, BTI) and any client-restricted tickers.
    """
    if ratings is None:
        ratings = ["Strong Buy", "Buy"]
    rating_list = ", ".join(f"'{r}'" for r in ratings)

    excluded = ["MO", "PM", "BTI"]
    if exclude_tickers:
        excluded += exclude_tickers
    excl_list = ", ".join(f"'{t}'" for t in excluded)

    query = f"""
        SELECT
            s.ticker,
            s.name,
            s.sector,
            s.industry,
            s.scalemarketcap,
            p.close     AS price,
            p.marketcap,
            p.pb,
            r.recommendation
        FROM stocks s
        JOIN prices p ON s.ticker = p.ticker
        JOIN recommendations r ON s.ticker = r.ticker
        WHERE s.sector = '{sector}'
          AND r.recommendation IN ({rating_list})
          AND s.ticker NOT IN ({excl_list})
          AND s.scalemarketcap IN ('6 - Mega', '5 - Large')
        ORDER BY p.marketcap DESC
        LIMIT 10
    """
    return run_sql(query)


def get_db_source() -> str:
    """Return which database is being used (for health endpoint)."""
    try:
        _, source = _get_conn()
        return source
    except Exception:
        return "unavailable"
