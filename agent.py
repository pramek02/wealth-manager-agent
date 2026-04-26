"""
Claude AI Agent — Wealth Manager Trading Plan Generator.

Agentic loop with 5 tools:
  1. get_portfolio_summary        → full enriched portfolio
  2. get_analyst_ratings          → MotherDuck recommendations for any tickers
  3. calculate_tax_impact         → specific-ID lot analysis for a proposed sale
  4. find_stocks_by_sector        → screen MotherDuck for buy candidates
  5. get_harvesting_opportunities → positions with unrealized losses

Client context baked into the system prompt:
  - Margaret & David Chen, Texas (no state tax)
  - Specific ID, prefer highest cost basis
  - Avoid STCG unless stock is rated Sell
  - No tobacco, no crypto
  - ±3pp rebalancing tolerance
"""
import os
import json
import anthropic
from portfolio_manager import build_enriched_portfolio
from tax_calculator import calculate_tax_impact, find_harvesting_opportunities
from db import get_prices_and_ratings, get_sector_candidates

_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
client = anthropic.Anthropic(api_key=_API_KEY)
MODEL = "claude-sonnet-4-5"

# ── Tool schemas ─────────────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "get_portfolio_summary",
        "description": (
            "Returns the complete enriched portfolio for Margaret & David Chen: "
            "all 49 positions with live prices from MotherDuck, P&L by position, "
            "sector weights vs. IPS targets, drift indicators, and concentration flags. "
            "Always call this first."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_analyst_ratings",
        "description": (
            "Fetches analyst recommendations from MotherDuck for any list of tickers. "
            "Recommendations are derived from P/B percentile: "
            "bottom 10% = Strong Buy, 10–30% = Buy, 30–70% = Hold, top 30% = Sell. "
            "Use this to check both current holdings and prospective buy candidates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of ticker symbols to look up",
                }
            },
            "required": ["tickers"],
        },
    },
    {
        "name": "calculate_tax_impact",
        "description": (
            "Calculates the full tax impact of selling shares in a position, "
            "using Specific Identification — highest cost-basis lots selected first "
            "to minimize capital gains. "
            "Returns lot-level breakdown, LT vs ST gains, total tax at Texas rates "
            "(20% federal LTCG + 3.8% NIIT = 23.8%; 32% + 3.8% = 35.8% for STCG), "
            "net after-tax proceeds, and recommendation on timing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Ticker symbol of position to analyze",
                },
                "shares_to_sell": {
                    "type": "integer",
                    "description": "Number of shares to sell",
                },
            },
            "required": ["ticker", "shares_to_sell"],
        },
    },
    {
        "name": "find_stocks_by_sector",
        "description": (
            "Screens MotherDuck for Mega/Large-cap stocks in a given sector with "
            "Strong Buy or Buy analyst ratings. Use this to find candidates to BUY "
            "when a sector is underweight. Excludes client-restricted tickers (MO, PM, BTI)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {
                    "type": "string",
                    "description": (
                        "Sector name. Must match: Technology, Financial Services, Healthcare, "
                        "Consumer Cyclical, Communication Services, Industrials, "
                        "Consumer Defensive, Energy, Real Estate, Basic Materials, Utilities"
                    ),
                },
                "exclude_already_held": {
                    "type": "boolean",
                    "description": "If true, exclude tickers already in the portfolio",
                },
            },
            "required": ["sector"],
        },
    },
    {
        "name": "get_harvesting_opportunities",
        "description": (
            "Returns all portfolio positions with unrealized losses, ranked by loss size. "
            "Each entry includes the estimated federal tax benefit from harvesting. "
            "Remember: 30-day wash-sale rule applies — cannot repurchase "
            "substantially identical securities within 30 days."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

# ── Tool dispatcher ───────────────────────────────────────────────────────────
def execute_tool(name: str, tool_input: dict, _portfolio_cache: dict) -> str:
    try:
        if name == "get_portfolio_summary":
            data = build_enriched_portfolio()
            _portfolio_cache.update(data)  # cache for subsequent tool calls
            # Trim lots detail to save tokens
            slim = {k: v for k, v in data.items() if k != "positions"}
            slim["positions"] = [
                {k: v for k, v in p.items() if k != "lots"}
                for p in data["positions"]
            ]
            return json.dumps(slim, default=str)

        elif name == "get_analyst_ratings":
            tickers = tool_input.get("tickers", [])
            df = get_prices_and_ratings(tickers)
            records = df[["ticker", "name", "sector", "price", "pb", "recommendation"]].to_dict("records")
            return json.dumps(records)

        elif name == "calculate_tax_impact":
            ticker = tool_input["ticker"]
            shares_to_sell = int(tool_input["shares_to_sell"])
            positions = _portfolio_cache.get("positions") or build_enriched_portfolio()["positions"]
            pos = next((p for p in positions if p["ticker"] == ticker), None)
            if not pos:
                return json.dumps({"error": f"{ticker} not found in portfolio"})
            result = calculate_tax_impact(
                ticker=ticker,
                shares_to_sell=shares_to_sell,
                current_price=pos["price"],
                lots=pos["lots"],
            )
            return json.dumps(result, default=str)

        elif name == "find_stocks_by_sector":
            sector = tool_input["sector"]
            exclude_held = tool_input.get("exclude_already_held", True)
            held = [p["ticker"] for p in _portfolio_cache.get("positions", [])]
            df = get_sector_candidates(
                sector=sector,
                ratings=["Strong Buy", "Buy"],
                exclude_tickers=held if exclude_held else None,
            )
            return json.dumps(df.to_dict("records"))

        elif name == "get_harvesting_opportunities":
            positions = _portfolio_cache.get("positions") or build_enriched_portfolio()["positions"]
            opps = find_harvesting_opportunities(positions)
            return json.dumps(opps)

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a professional portfolio analyst AI serving as decision support for a wealth manager.

CLIENT: Margaret & David Chen
- Married, filing jointly | Texas (zero state income tax)
- Taxable brokerage account, ~$500K
- Time horizon: 20+ years | Risk profile: Moderate

TAX RULES (critical — follow exactly):
- LTCG rate: 23.8% effective (20% federal + 3.8% NIIT)
- STCG rate: 35.8% effective (32% federal + 3.8% NIIT)
- Specific Identification: always select highest cost-basis lots first
- Avoid short-term gains (< 1 year held) unless the stock has a Sell rating
- If a short-term lot is within 30 days of turning long-term, recommend waiting
- Wash-sale rule: no repurchase within 30 days of a loss harvest

ANALYST METHODOLOGY:
- Recommendations are P/B percentile-based (relative value signal)
- Strong Buy = cheapest 10% by P/B | Buy = 10–30th pct | Hold = 30–70th | Sell = top 30%

PORTFOLIO CONSTRAINTS:
- Max single-stock concentration: 5% of total portfolio
- Sector tolerance: ±3 percentage points from IPS target weights
- Excluded: MO, PM, BTI (tobacco) | No cryptocurrency equities
- Money Market always = 10% of total portfolio

REBALANCING LOGIC:
- Identify sectors >3pp overweight → look for Sell-rated holdings to trim/exit
- Identify sectors >3pp underweight → find Strong Buy/Buy-rated stocks to add
- For sells: always calculate tax impact before recommending; prefer long-term lots
- Prioritize sales that are: (a) long-term gains, (b) Sell-rated, (c) overweight sector

YOUR WORKFLOW:
1. get_portfolio_summary — understand full picture
2. Identify overweight sectors with Sell-rated holdings → get_analyst_ratings
3. For each sell candidate → calculate_tax_impact (use actual lot data)
4. get_harvesting_opportunities — find loss positions
5. For underweight sectors → find_stocks_by_sector
6. Synthesize into a complete, tax-optimized trading plan

OUTPUT: Return a JSON object with this exact structure:
{
  "executive_summary": "3-4 sentence summary for the wealth manager",
  "portfolio_health_score": <0-100 integer>,
  "key_findings": ["finding 1", "finding 2", ...],
  "sector_status": {
    "<sector>": {"actual": X, "target": Y, "drift": Z, "action": "...", "status": "..."}
  },
  "recommended_sells": [
    {
      "ticker": "...", "shares": N, "rationale": "...",
      "analyst_rating": "...", "estimated_proceeds": N,
      "tax_analysis": "...", "net_after_tax": N, "priority": "HIGH/MEDIUM/LOW"
    }
  ],
  "recommended_buys": [
    {
      "ticker": "...", "shares": N, "sector": "...", "rationale": "...",
      "analyst_rating": "...", "pb_ratio": N, "estimated_cost": N, "priority": "HIGH/MEDIUM/LOW"
    }
  ],
  "tax_loss_harvesting": [
    {
      "ticker": "...", "action": "...", "unrealized_loss": N,
      "tax_benefit": N, "wash_sale_note": "..."
    }
  ],
  "trading_plan_narrative": "Multi-paragraph plain-English explanation of the full plan",
  "risk_considerations": ["risk 1", ...],
  "total_estimated_trades": N,
  "total_estimated_tax_cost": N,
  "total_estimated_tax_savings": N,
  "expected_portfolio_improvement": "..."
}"""


def run_agent() -> dict:
    """Run the full agentic loop and return the structured trading plan."""
    messages = [
        {
            "role": "user",
            "content": (
                "Please analyze the portfolio for Margaret and David Chen and generate "
                "a complete, tax-optimized trading plan. Use all available tools to "
                "gather data before forming recommendations. Be specific about lot selection, "
                "tax impacts, and timing. Return the final analysis as a JSON trading plan."
            ),
        }
    ]

    _portfolio_cache: dict = {}
    tool_calls_log = []

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    output = execute_tool(block.name, block.input, _portfolio_cache)
                    # Anthropic requires non-empty content in tool results
                    if not output or output.strip() == "":
                        output = json.dumps({"status": "ok", "result": "empty"})
                    tool_calls_log.append({"tool": block.name, "input": block.input})
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                    })
            if results:
                messages.append({"role": "user", "content": results})
        else:
            break

    # Extract final text + parse JSON
    final_text = "".join(
        block.text for block in response.content if hasattr(block, "text")
    )
    plan = _extract_json(final_text)
    plan["_tool_calls"] = tool_calls_log
    plan["_raw_response"] = final_text
    return plan


def _extract_json(text: str) -> dict:
    import re
    m = re.search(r"```json\s*([\s\S]+?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    return {
        "trading_plan_narrative": text,
        "executive_summary": "Analysis complete — see narrative.",
        "recommended_sells": [],
        "recommended_buys": [],
        "tax_loss_harvesting": [],
        "key_findings": [],
        "risk_considerations": [],
    }
