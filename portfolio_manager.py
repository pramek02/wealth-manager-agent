"""
Portfolio manager: loads the 167 tax lots from Excel, enriches them with
live MotherDuck prices and analyst ratings, computes position-level summaries,
sector weights, and drift from the client's target allocation.

Client: Margaret & David Chen — Texas (no state income tax)
Account: ~$500K taxable brokerage, 49 stocks, 167 purchase lots (2020–2025)
"""
import json
from pathlib import Path
from datetime import date, datetime

import pandas as pd

from db import get_prices_and_ratings

DATA_DIR = Path(__file__).parent / "data"

# ── Client profile ───────────────────────────────────────────────────────────
CLIENT = {
    "name": "Margaret & David Chen",
    "manager": "Wealth Manager AI Agent",
    "account_type": "Taxable Brokerage",
    "state": "Texas",
    "filing_status": "Married Filing Jointly",
    # Federal capital gains tax rates (MFJ, estimated high-income earners)
    "tax_rate_ltcg": 0.20,       # 20% federal LTCG (high earners)
    "tax_rate_stcg": 0.32,       # 32% federal ordinary income bracket
    "tax_rate_state": 0.00,      # Texas — no state income tax
    "niit_rate": 0.038,          # 3.8% Net Investment Income Tax
    "max_single_stock_pct": 5.0, # 5% concentration limit
    "drift_tolerance_pct": 3.0,  # ±3 pp rebalancing threshold
    "excluded_tickers": ["MO", "PM", "BTI"],  # no tobacco
}

# Target sector weights (from client IPS — based on US market cap, 90% equity + 10% MMKT)
SECTOR_TARGETS = {
    "Money Market":          10.00,
    "Technology":            25.38,
    "Financial Services":    13.19,
    "Healthcare":             9.66,
    "Consumer Cyclical":      9.33,
    "Communication Services": 8.40,
    "Industrials":            7.91,
    "Consumer Defensive":     5.48,
    "Energy":                 3.74,
    "Real Estate":            2.40,
    "Basic Materials":        2.32,
    "Utilities":              2.19,
}


def load_lots() -> pd.DataFrame:
    """Load the 167 purchase lots from the Excel file."""
    path = DATA_DIR / "portfolio_lots.xlsx"
    df = pd.read_excel(path, sheet_name="Purchase Lots")
    df["Date"] = pd.to_datetime(df["Date"])
    df["cost_per_share"] = df["Cost"] / df["Shares"]
    return df


def days_held(purchase_date: pd.Timestamp) -> int:
    return (date.today() - purchase_date.date()).days


def is_long_term(purchase_date: pd.Timestamp) -> bool:
    return days_held(purchase_date) > 365


def build_enriched_portfolio() -> dict:
    """
    Core function: loads lots, fetches live prices + ratings, builds full
    portfolio summary with positions, sector weights, and drift.
    """
    lots_df = load_lots()
    tickers = lots_df["Ticker"].unique().tolist()

    # Fetch prices + ratings from MotherDuck
    market_df = get_prices_and_ratings(tickers)
    market = market_df.set_index("ticker").to_dict("index")

    # ── Position-level aggregation ───────────────────────────────────────────
    positions = []
    for ticker, grp in lots_df.groupby("Ticker"):
        mkt = market.get(ticker, {})
        price = mkt.get("price", None)
        if price is None or pd.isna(price):
            continue  # skip if no price data

        total_shares = int(grp["Shares"].sum())
        total_cost = float(grp["Cost"].sum())
        market_value = price * total_shares
        unrealized_gain = market_value - total_cost
        gain_pct = (unrealized_gain / total_cost * 100) if total_cost else 0

        # Lots sorted by cost_per_share DESC (specific ID: highest cost basis first)
        lots_sorted = grp.sort_values("cost_per_share", ascending=False)
        lot_list = [
            {
                "lot_date": row["Date"].strftime("%Y-%m-%d"),
                "shares": int(row["Shares"]),
                "cost_per_share": round(float(row["cost_per_share"]), 4),
                "total_cost": round(float(row["Cost"]), 2),
                "days_held": days_held(row["Date"]),
                "is_long_term": is_long_term(row["Date"]),
                "holding_type": "Long-Term" if is_long_term(row["Date"]) else "Short-Term",
            }
            for _, row in lots_sorted.iterrows()
        ]

        lt_shares = sum(l["shares"] for l in lot_list if l["is_long_term"])
        st_shares = total_shares - lt_shares

        # Analyst rating
        recommendation = mkt.get("recommendation", "Hold")
        pb = mkt.get("pb", None)
        analyst_target = None  # DB doesn't have price targets; use P/B fair value

        positions.append({
            "ticker": ticker,
            "name": mkt.get("name", ticker),
            "sector": mkt.get("sector") or grp.iloc[0]["Sector"],
            "industry": mkt.get("industry") or grp.iloc[0]["Industry"],
            "scalemarketcap": mkt.get("scalemarketcap", ""),
            "shares": total_shares,
            "price": round(price, 2),
            "market_value": round(market_value, 2),
            "total_cost": round(total_cost, 2),
            "avg_cost_per_share": round(total_cost / total_shares, 4) if total_shares else 0,
            "unrealized_gain": round(unrealized_gain, 2),
            "gain_pct": round(gain_pct, 2),
            "lt_shares": lt_shares,
            "st_shares": st_shares,
            "num_lots": len(lot_list),
            "lots": lot_list,
            "recommendation": recommendation,
            "pb": round(float(pb), 2) if pb and not pd.isna(pb) else None,
            "marketcap": mkt.get("marketcap"),
        })

    # ── Total equity value ───────────────────────────────────────────────────
    equity_value = sum(p["market_value"] for p in positions)
    # Client holds 10% money market → total portfolio = equity / 0.90
    total_portfolio_value = equity_value / 0.90 if equity_value else 1.0
    mmkt_value = total_portfolio_value * 0.10

    total_cost_basis = sum(p["total_cost"] for p in positions)
    total_unrealized_gain = equity_value - total_cost_basis

    # ── Sector weights (as % of total portfolio incl. money market) ──────────
    sector_values: dict[str, float] = {"Money Market": mmkt_value}
    for p in positions:
        s = p["sector"]
        sector_values[s] = sector_values.get(s, 0) + p["market_value"]

    sector_weights = {
        s: round(v / total_portfolio_value * 100, 2)
        for s, v in sector_values.items()
    }

    # ── Drift vs targets ─────────────────────────────────────────────────────
    all_sectors = set(list(SECTOR_TARGETS.keys()) + list(sector_weights.keys()))
    sector_drift = {}
    tol = CLIENT["drift_tolerance_pct"]
    for s in all_sectors:
        actual = sector_weights.get(s, 0.0)
        target = SECTOR_TARGETS.get(s, 0.0)
        drift = round(actual - target, 2)
        status = (
            "OVERWEIGHT" if drift > tol else
            "UNDERWEIGHT" if drift < -tol else
            "ON TARGET"
        )
        sector_drift[s] = {
            "actual": actual,
            "target": target,
            "drift": drift,
            "status": status,
            "value": round(sector_values.get(s, 0), 2),
        }

    # ── Concentration check ──────────────────────────────────────────────────
    max_pct = CLIENT["max_single_stock_pct"]
    concentration_flags = [
        p["ticker"] for p in positions
        if (p["market_value"] / total_portfolio_value * 100) > max_pct
    ]

    return {
        "client_name": CLIENT["name"],
        "account_type": CLIENT["account_type"],
        "state": CLIENT["state"],
        "as_of_date": date.today().isoformat(),
        "positions": positions,
        "num_positions": len(positions),
        "equity_value": round(equity_value, 2),
        "mmkt_value": round(mmkt_value, 2),
        "total_portfolio_value": round(total_portfolio_value, 2),
        "total_cost_basis": round(total_cost_basis, 2),
        "total_unrealized_gain": round(total_unrealized_gain, 2),
        "total_return_pct": round(total_unrealized_gain / total_cost_basis * 100, 2) if total_cost_basis else 0,
        "sector_weights": sector_weights,
        "sector_drift": sector_drift,
        "sector_targets": SECTOR_TARGETS,
        "concentration_flags": concentration_flags,
        "tax_rates": {
            "ltcg": CLIENT["tax_rate_ltcg"],
            "stcg": CLIENT["tax_rate_stcg"],
            "state": CLIENT["tax_rate_state"],
            "niit": CLIENT["niit_rate"],
        },
        "drift_tolerance_pct": tol,
    }
