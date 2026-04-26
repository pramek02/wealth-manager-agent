"""
FastAPI application — Wealth Manager AI Agent
Client: Margaret & David Chen | Texas | Taxable Brokerage

Endpoints:
  GET  /                    → Serve dashboard UI
  GET  /api/portfolio       → Enriched portfolio (MotherDuck prices + ratings)
  GET  /api/analysis        → Run Claude agent (cached 30 min)
  GET  /api/report          → Download PDF report
  POST /api/portfolio/reset → Clear cache
  GET  /api/health          → Health check
"""
import os
import time
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from portfolio_manager import build_enriched_portfolio
from pdf_generator import generate_report
from tax_calculator import find_harvesting_opportunities

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Wealth Manager AI Agent",
    description="AI-powered portfolio analysis for Margaret & David Chen",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Cache: avoids re-running agent on every request
_cache: dict = {"portfolio": None, "analysis": None, "ts": 0}
CACHE_TTL = 1800  # 30 minutes


def _expired() -> bool:
    return (time.time() - _cache["ts"]) > CACHE_TTL


@app.get("/", response_class=HTMLResponse)
async def root():
    p = static_dir / "index.html"
    return FileResponse(str(p)) if p.exists() else HTMLResponse("<h1>Wealth Manager AI</h1>")


@app.get("/api/portfolio")
async def get_portfolio():
    """Live portfolio: MotherDuck prices, sector weights, drift from IPS targets."""
    try:
        if _cache["portfolio"] is None or _expired():
            logger.info("Building portfolio…")
            _cache["portfolio"] = build_enriched_portfolio()
            _cache["ts"] = time.time()
        return _cache["portfolio"]
    except Exception as e:
        logger.error(f"Portfolio error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analysis")
async def run_analysis():
    """
    Runs the Claude AI agent agentic loop.
    Uses 5 tools to analyze portfolio, check analyst ratings, compute tax impact,
    screen buy candidates, and identify harvesting opportunities.
    Returns a structured JSON trading plan.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not set. Add it in Railway environment variables.",
        )
    if _cache["analysis"] is not None and not _expired():
        return _cache["analysis"]
    try:
        logger.info("Running Claude agent…")
        from agent import run_agent
        result = run_agent()
        _cache["analysis"] = result
        _cache["ts"] = time.time()
        return result
    except Exception as e:
        logger.error(f"Agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/report")
async def download_report():
    """Generate and return the full PDF trading plan report."""
    try:
        if _cache["portfolio"] is None or _expired():
            _cache["portfolio"] = build_enriched_portfolio()

        if _cache["analysis"] is None or _expired():
            if os.environ.get("ANTHROPIC_API_KEY"):
                from agent import run_agent
                _cache["analysis"] = run_agent()
            else:
                _cache["analysis"] = _demo_plan(_cache["portfolio"])

        logger.info("Generating PDF…")
        pdf = generate_report(_cache["portfolio"], _cache["analysis"])
        fname = f"chen_trading_plan_{time.strftime('%Y%m%d')}.pdf"
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    except Exception as e:
        logger.error(f"PDF error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/portfolio/reset")
async def reset_cache():
    _cache.update({"portfolio": None, "analysis": None, "ts": 0})
    return {"message": "Cache cleared."}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "api_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "motherduck_token_set": bool(os.environ.get("MOTHERDUCK_TOKEN")),
        "cache_age_s": int(time.time() - _cache["ts"]) if _cache["ts"] else None,
    }


def _demo_plan(portfolio: dict) -> dict:
    """Fallback plan (no API key) based purely on sector drift data."""
    drift = portfolio.get("sector_drift", {})
    overweight = [s for s, d in drift.items() if d["status"] == "OVERWEIGHT"]
    underweight = [s for s, d in drift.items() if d["status"] == "UNDERWEIGHT"]
    positions = portfolio.get("positions", [])

    harvesting = find_harvesting_opportunities(positions)

    sells = []
    for p in positions:
        if p["sector"] in overweight and p["recommendation"] in ("Sell", "Hold"):
            sells.append({
                "ticker": p["ticker"],
                "shares": p["shares"] // 4,
                "rationale": (
                    f"{p['sector']} is {drift.get(p['sector'], {}).get('drift', 0):+.1f}% "
                    f"vs target; analyst rating: {p['recommendation']}"
                ),
                "analyst_rating": p["recommendation"],
                "estimated_proceeds": round((p["shares"] // 4) * p["price"], 0),
                "tax_analysis": "Long-term gain — 23.8% effective rate (TX, no state tax)",
                "net_after_tax": round((p["shares"] // 4) * p["price"] * 0.762, 0),
                "priority": "HIGH" if p["recommendation"] == "Sell" else "MEDIUM",
            })

    return {
        "executive_summary": (
            f"Portfolio holds {len(positions)} equity positions (~${portfolio['equity_value']:,.0f}) "
            f"plus ${portfolio['mmkt_value']:,.0f} money market "
            f"(total ~${portfolio['total_portfolio_value']:,.0f}). "
            f"Sectors {', '.join(overweight)} are overweight vs. IPS targets; "
            f"{', '.join(underweight)} are underweight. "
            "A rebalancing program with tax-aware lot selection is recommended."
        ),
        "portfolio_health_score": 68,
        "key_findings": [
            f"Total portfolio: ${portfolio['total_portfolio_value']:,.0f} | "
            f"Equity return: {portfolio['total_return_pct']:.1f}%",
            f"Overweight: {', '.join(overweight) if overweight else 'None'}",
            f"Underweight: {', '.join(underweight) if underweight else 'None'}",
            f"{len(harvesting)} position(s) eligible for tax-loss harvesting",
            "Texas: zero state income tax — federal rates only (LTCG 23.8%, STCG 35.8%)",
            "Specific ID preferred: sell highest-cost-basis lots first to minimize gains",
        ],
        "recommended_sells": sells[:5],
        "recommended_buys": [],
        "tax_loss_harvesting": [
            {
                "ticker": h["ticker"],
                "action": f"Harvest ${abs(h['unrealized_loss']):,.0f} loss",
                "unrealized_loss": h["unrealized_loss"],
                "tax_benefit": h["estimated_tax_benefit"],
                "wash_sale_note": (
                    "Do not repurchase within 30 days. "
                    "Consider a similar ETF to maintain sector exposure."
                ),
            }
            for h in harvesting[:4]
        ],
        "trading_plan_narrative": (
            "DEMO MODE — AI agent requires ANTHROPIC_API_KEY environment variable.\n\n"
            "In production, Claude runs an agentic loop calling 5 specialized tools:\n\n"
            "Tool 1: get_portfolio_summary — Loads 167 tax lots from Excel, fetches live "
            "prices from MotherDuck, computes sector weights vs. IPS targets.\n\n"
            "Tool 2: get_analyst_ratings — Queries MotherDuck recommendations (P/B "
            "percentile-based: Strong Buy = bottom 10%, Sell = top 30%).\n\n"
            "Tool 3: calculate_tax_impact — Specific Identification lot selection: "
            "highest cost-basis lots first. Applies 23.8% LTCG / 35.8% STCG (Texas = $0 state).\n\n"
            "Tool 4: find_stocks_by_sector — Screens MotherDuck for Strong Buy / Buy rated "
            "Mega/Large cap stocks in underweight sectors, excluding restricted tickers.\n\n"
            "Tool 5: get_harvesting_opportunities — Identifies loss positions for tax-loss "
            "harvesting with 30-day wash-sale rule guidance.\n\n"
            "Claude then synthesizes all five data streams into a prioritized, tax-optimal "
            "trading plan tailored to Margaret and David Chen's IPS."
        ),
        "risk_considerations": [
            "Wash-sale rule: wait 31+ days before repurchasing any harvested position",
            "Short-term lots (< 1 year): avoid selling unless Sell-rated; 35.8% rate",
            "Specific ID requires broker confirmation before each trade",
            "NIIT (3.8%) applies to net investment income — factor into trade sizing",
            "Analyst ratings are relative P/B value signals, not fundamental analysis",
        ],
        "total_estimated_trades": len(sells),
        "total_estimated_tax_cost": sum(
            s.get("estimated_proceeds", 0) * 0.238 for s in sells
        ),
        "total_estimated_tax_savings": sum(
            h.get("estimated_tax_benefit", 0) for h in harvesting[:4]
        ),
        "expected_portfolio_improvement": (
            "Sectors realigned to within ±3pp of IPS targets; "
            "tax-loss harvesting offsets rebalancing gains"
        ),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
