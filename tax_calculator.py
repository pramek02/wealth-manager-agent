"""
Tax calculator for Margaret & David Chen.

Key rules:
- Texas: ZERO state income tax
- Federal LTCG: 20% (high-income earners, MFJ)
- Federal STCG: 32% (ordinary income bracket)
- NIIT: 3.8% on net investment income above threshold
- Specific Identification: prefer HIGHEST cost-basis lots first (minimizes gain)
- Avoid short-term gains unless recommendation is strong (Sell rating)
- Wash-sale: do not repurchase within 30 days of selling at a loss
"""
from datetime import date, datetime
from typing import Optional


# ── Tax rates ────────────────────────────────────────────────────────────────
LTCG_RATE   = 0.20    # Federal long-term capital gains
STCG_RATE   = 0.32    # Federal short-term (ordinary income)
NIIT_RATE   = 0.038   # Net Investment Income Tax (applies to gains)
STATE_RATE  = 0.00    # Texas — no state income tax

# Effective all-in rates
EFFECTIVE_LTCG = LTCG_RATE + NIIT_RATE   # 23.8%
EFFECTIVE_STCG = STCG_RATE + NIIT_RATE   # 35.8%


def select_lots_for_sale(lots: list[dict], shares_to_sell: int) -> list[dict]:
    """
    Specific Identification: select lots starting from the HIGHEST cost basis
    (minimizes taxable gain). Returns a list of selected lot slices.

    Each lot dict must have: lot_date, shares, cost_per_share, is_long_term
    Lots should already be sorted by cost_per_share DESC.
    """
    selected = []
    remaining = shares_to_sell

    for lot in lots:
        if remaining <= 0:
            break
        take = min(lot["shares"], remaining)
        selected.append({
            "lot_date": lot["lot_date"],
            "shares_sold": take,
            "cost_per_share": lot["cost_per_share"],
            "total_cost": round(take * lot["cost_per_share"], 2),
            "is_long_term": lot["is_long_term"],
            "holding_type": "Long-Term" if lot["is_long_term"] else "Short-Term",
            "days_held": lot["days_held"],
        })
        remaining -= take

    return selected


def calculate_tax_impact(
    ticker: str,
    shares_to_sell: int,
    current_price: float,
    lots: list[dict],
) -> dict:
    """
    Full tax analysis for a proposed sale using specific identification
    (highest cost basis first).

    Args:
        ticker: stock symbol
        shares_to_sell: number of shares to sell
        current_price: current market price
        lots: list of lot dicts sorted by cost_per_share DESC
    """
    total_shares = sum(l["shares"] for l in lots)
    shares_to_sell = min(shares_to_sell, total_shares)

    selected = select_lots_for_sale(lots, shares_to_sell)

    gross_proceeds = round(current_price * shares_to_sell, 2)
    total_basis = round(sum(s["total_cost"] for s in selected), 2)
    total_gain = round(gross_proceeds - total_basis, 2)

    # Split by holding type
    lt_gain = 0.0
    st_gain = 0.0
    for s in selected:
        proceeds_lot = current_price * s["shares_sold"]
        gain_lot = proceeds_lot - s["total_cost"]
        if s["is_long_term"]:
            lt_gain += gain_lot
        else:
            st_gain += gain_lot
    lt_gain = round(lt_gain, 2)
    st_gain = round(st_gain, 2)

    # Tax estimates
    lt_tax = round(max(lt_gain, 0) * EFFECTIVE_LTCG, 2)
    st_tax = round(max(st_gain, 0) * EFFECTIVE_STCG, 2)
    loss_benefit = round(min(total_gain, 0) * EFFECTIVE_LTCG, 2)  # negative = tax savings

    total_tax = round(lt_tax + st_tax, 2)
    net_proceeds = round(gross_proceeds - total_tax, 2)

    # Check for lots close to long-term threshold
    st_lots_near_lt = [
        s for s in selected
        if not s["is_long_term"] and s["days_held"] >= 335  # within 30 days of 1-year
    ]
    days_to_lt = (
        min(365 - s["days_held"] for s in st_lots_near_lt)
        if st_lots_near_lt else None
    )
    st_tax_avoided = round(st_gain * (EFFECTIVE_STCG - EFFECTIVE_LTCG), 2) if st_gain > 0 else 0

    return {
        "ticker": ticker,
        "shares_to_sell": shares_to_sell,
        "current_price": current_price,
        "gross_proceeds": gross_proceeds,
        "total_cost_basis": total_basis,
        "total_gain": total_gain,
        "lt_gain": lt_gain,
        "st_gain": st_gain,
        "lt_tax": lt_tax,
        "st_tax": st_tax,
        "total_tax_estimated": total_tax,
        "tax_as_pct_proceeds": round(total_tax / gross_proceeds * 100, 1) if gross_proceeds else 0,
        "net_after_tax_proceeds": net_proceeds,
        "selected_lots": selected,
        "days_to_long_term": days_to_lt,
        "tax_savings_from_waiting": st_tax_avoided if days_to_lt else 0,
        "loss_tax_benefit": abs(loss_benefit) if total_gain < 0 else 0,
        "recommendation": _tax_recommendation(
            total_gain, lt_gain, st_gain, days_to_lt, st_tax_avoided, total_tax
        ),
    }


def _tax_recommendation(
    total_gain: float,
    lt_gain: float,
    st_gain: float,
    days_to_lt: Optional[int],
    st_tax_savings: float,
    total_tax: float,
) -> str:
    if total_gain < 0:
        benefit = abs(total_gain) * EFFECTIVE_LTCG
        return (
            f"HARVEST LOSS — Realizing ${abs(total_gain):,.0f} loss saves "
            f"~${benefit:,.0f} in federal taxes. Watch 30-day wash-sale window."
        )
    if days_to_lt and st_gain > 0:
        return (
            f"WAIT {days_to_lt} DAYS — Short-term lot(s) convert to long-term, "
            f"saving ~${st_tax_savings:,.0f} in taxes (ST 35.8% → LT 23.8%)."
        )
    if st_gain > lt_gain and st_gain > 500:
        return (
            f"SHORT-TERM GAIN WARNING — ${st_gain:,.0f} taxed at 35.8% "
            f"(${round(st_gain * EFFECTIVE_STCG):,.0f} tax). Consider deferring "
            f"or using higher-basis lots."
        )
    return (
        f"LONG-TERM GAIN — ${lt_gain:,.0f} taxed at 23.8% effective rate "
        f"(${total_tax:,.0f} estimated tax). Favorable treatment."
    )


def find_harvesting_opportunities(positions: list[dict]) -> list[dict]:
    """
    Find all positions with unrealized losses that could be harvested.
    Returns sorted by size of loss (largest first).
    """
    opps = []
    for p in positions:
        if p["unrealized_gain"] < 0:
            loss = abs(p["unrealized_gain"])
            tax_benefit = loss * EFFECTIVE_LTCG  # conservative: use LTCG rate
            opps.append({
                "ticker": p["ticker"],
                "name": p["name"],
                "sector": p["sector"],
                "shares": p["shares"],
                "price": p["price"],
                "unrealized_loss": p["unrealized_gain"],
                "loss_pct": p["gain_pct"],
                "estimated_tax_benefit": round(tax_benefit, 2),
                "recommendation": p["recommendation"],
                "lt_shares": p["lt_shares"],
                "st_shares": p["st_shares"],
            })
    return sorted(opps, key=lambda x: x["unrealized_loss"])
