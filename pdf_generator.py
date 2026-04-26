"""
PDF Report Generator using ReportLab.
Produces a professional multi-page wealth management report
with portfolio tables, sector charts, analyst ratings, and the AI trading plan.
"""
import io
import json
from datetime import date
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics import renderPDF


# ─── Color Palette ────────────────────────────────────────────────────────────
NAVY = colors.HexColor("#1a2f5a")
BLUE = colors.HexColor("#2563eb")
LIGHT_BLUE = colors.HexColor("#eff6ff")
GREEN = colors.HexColor("#16a34a")
RED = colors.HexColor("#dc2626")
ORANGE = colors.HexColor("#ea580c")
GRAY = colors.HexColor("#6b7280")
LIGHT_GRAY = colors.HexColor("#f9fafb")
MID_GRAY = colors.HexColor("#e5e7eb")
WHITE = colors.white
GOLD = colors.HexColor("#d97706")


def build_styles():
    styles = getSampleStyleSheet()
    custom = {
        "title": ParagraphStyle("title", fontSize=22, textColor=NAVY,
                                fontName="Helvetica-Bold", spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", fontSize=11, textColor=GRAY,
                                   fontName="Helvetica", spaceAfter=2),
        "h1": ParagraphStyle("h1", fontSize=14, textColor=NAVY,
                             fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontSize=11, textColor=BLUE,
                             fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", fontSize=9, textColor=colors.black,
                               fontName="Helvetica", leading=13, spaceAfter=4),
        "body_justify": ParagraphStyle("body_justify", fontSize=9, textColor=colors.black,
                                       fontName="Helvetica", leading=14, spaceAfter=6,
                                       alignment=TA_JUSTIFY),
        "caption": ParagraphStyle("caption", fontSize=8, textColor=GRAY,
                                  fontName="Helvetica-Oblique", spaceAfter=2),
        "metric_label": ParagraphStyle("metric_label", fontSize=8, textColor=GRAY,
                                       fontName="Helvetica"),
        "metric_value": ParagraphStyle("metric_value", fontSize=16, textColor=NAVY,
                                       fontName="Helvetica-Bold"),
        "tag_green": ParagraphStyle("tag_green", fontSize=8, textColor=GREEN,
                                    fontName="Helvetica-Bold"),
        "tag_red": ParagraphStyle("tag_red", fontSize=8, textColor=RED,
                                  fontName="Helvetica-Bold"),
        "tag_orange": ParagraphStyle("tag_orange", fontSize=8, textColor=ORANGE,
                                     fontName="Helvetica-Bold"),
        "footer": ParagraphStyle("footer", fontSize=7.5, textColor=GRAY,
                                 fontName="Helvetica", alignment=TA_CENTER),
    }
    return custom


def _color_for_gain(val: float):
    if val > 0:
        return GREEN
    elif val < 0:
        return RED
    return GRAY


def _format_currency(val: float, decimals: int = 0) -> str:
    if val >= 0:
        return f"${val:,.{decimals}f}"
    return f"(${ abs(val):,.{decimals}f})"


def _format_pct(val: float) -> str:
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


def _consensus_color(c: str) -> colors.Color:
    mapping = {
        "Strong Buy": GREEN,
        "Buy": colors.HexColor("#22c55e"),
        "Hold": ORANGE,
        "Sell": RED,
        "Strong Sell": colors.HexColor("#7f1d1d")
    }
    return mapping.get(c, GRAY)


# ─── Page Header/Footer ───────────────────────────────────────────────────────
def make_page_header_footer(canvas, doc):
    canvas.saveState()
    w, h = letter
    # Header bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 36, w, 36, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.setFillColor(WHITE)
    canvas.drawString(0.5 * inch, h - 23, "MARGARET & DAVID CHEN — TAXABLE BROKERAGE ACCOUNT")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(w - 0.5 * inch, h - 23, f"AI Trading Plan | {date.today().strftime('%B %d, %Y')}")
    # Footer line
    canvas.setStrokeColor(MID_GRAY)
    canvas.setLineWidth(0.5)
    canvas.line(0.5 * inch, 0.55 * inch, w - 0.5 * inch, 0.55 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GRAY)
    canvas.drawString(0.5 * inch, 0.3 * inch,
                      "CONFIDENTIAL — For internal use only. Not for distribution. Past performance is not indicative of future results.")
    canvas.drawRightString(w - 0.5 * inch, 0.3 * inch, f"Page {doc.page}")
    canvas.restoreState()


# ─── Sector Bar Chart ─────────────────────────────────────────────────────────
def build_sector_chart(sector_drift: dict, width=5.5*inch, height=2.4*inch) -> Drawing:
    """Create a grouped bar chart: actual vs target sector weights."""
    sectors = sorted(
        [(s, d["actual"], d["target"]) for s, d in sector_drift.items() if d["target"] > 0 or d["actual"] > 0],
        key=lambda x: -x[2]
    )
    labels = [s[:14] for s, *_ in sectors]
    actual_vals = [s[1] for s in sectors]
    target_vals = [s[2] for s in sectors]

    drawing = Drawing(width, height)
    bc = VerticalBarChart()
    bc.x = 45
    bc.y = 30
    bc.width = width - 60
    bc.height = height - 55

    bc.data = [actual_vals, target_vals]
    bc.bars[0].fillColor = BLUE
    bc.bars[1].fillColor = MID_GRAY
    bc.bars[0].strokeColor = None
    bc.bars[1].strokeColor = None
    bc.groupSpacing = 8
    bc.barSpacing = 1
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max(max(actual_vals), max(target_vals)) + 3
    bc.valueAxis.valueStep = 5
    bc.valueAxis.labelTextFormat = "%g%%"
    bc.valueAxis.labels.fontSize = 7
    bc.categoryAxis.categoryNames = labels
    bc.categoryAxis.labels.fontSize = 7
    bc.categoryAxis.labels.angle = 35
    bc.categoryAxis.labels.dy = -10
    bc.categoryAxis.labels.dx = -3
    drawing.add(bc)

    # Legend
    drawing.add(Rect(45, height - 20, 10, 8, fillColor=BLUE, strokeColor=None))
    drawing.add(String(58, height - 14, "Actual", fontSize=8, fillColor=colors.black))
    drawing.add(Rect(100, height - 20, 10, 8, fillColor=MID_GRAY, strokeColor=None))
    drawing.add(String(113, height - 14, "Target", fontSize=8, fillColor=colors.black))

    return drawing


# ─── Main PDF Builder ─────────────────────────────────────────────────────────
def generate_report(portfolio: dict, trading_plan: dict) -> bytes:
    """
    Generate the complete PDF report.
    Returns bytes that can be sent as an HTTP response.
    """
    buffer = io.BytesIO()
    styles = build_styles()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.75 * inch,
        title="Wealth Manager AI Trading Plan",
        author="Claude AI Agent"
    )

    story = []

    # ── Cover Header ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("AI-Powered Portfolio Trading Plan", styles["title"]))
    story.append(Paragraph(
        f"Client: {portfolio.get('client_name', 'Margaret & David Chen')}  |  "
        f"{portfolio.get('account_type', 'Taxable Brokerage')}  |  "
        f"Texas (No State Income Tax)  |  {date.today().strftime('%B %d, %Y')}",
        styles["subtitle"]
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE, spaceAfter=12))

    # ── Executive Summary ─────────────────────────────────────────────────────
    exec_summary = trading_plan.get("executive_summary", "Portfolio analysis complete.")
    story.append(Paragraph("Executive Summary", styles["h1"]))
    story.append(Paragraph(exec_summary, styles["body_justify"]))

    # ── Portfolio Metrics Row ─────────────────────────────────────────────────
    total_val = portfolio.get("total_portfolio_value", portfolio.get("total_market_value", 0))
    total_gain = portfolio.get("total_unrealized_gain", 0)
    ret_pct = portfolio.get("total_return_pct", 0)
    score = trading_plan.get("portfolio_health_score", "—")

    metrics_data = [
        [
            _build_metric("Total Market Value", _format_currency(total_val), styles),
            _build_metric("Unrealized Gain/Loss",
                          _format_currency(total_gain),
                          styles, color=_color_for_gain(total_gain)),
            _build_metric("Total Return",
                          _format_pct(ret_pct),
                          styles, color=_color_for_gain(ret_pct)),
            _build_metric("Portfolio Health Score",
                          f"{score}/100",
                          styles, color=GREEN if isinstance(score, (int,float)) and score >= 70 else ORANGE)
        ]
    ]
    metrics_tbl = Table(metrics_data, colWidths=[1.65*inch]*4)
    metrics_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE),
        ("ROUNDEDCORNERS", [4]),
        ("BOX", (0, 0), (-1, -1), 1, BLUE),
        ("LINEAFTER", (0, 0), (2, 0), 0.5, MID_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(metrics_tbl)
    story.append(Spacer(1, 0.15 * inch))

    # ── Key Findings ──────────────────────────────────────────────────────────
    findings = trading_plan.get("key_findings", [])
    if findings:
        story.append(Paragraph("Key Findings", styles["h1"]))
        for i, f in enumerate(findings, 1):
            story.append(Paragraph(f"<b>{i}.</b>  {f}", styles["body"]))
        story.append(Spacer(1, 0.1 * inch))

    # ── Sector Exposure Analysis ───────────────────────────────────────────────
    story.append(Paragraph("Sector Exposure vs. Target Allocation", styles["h1"]))
    story.append(build_sector_chart(portfolio["sector_drift"]))
    story.append(Spacer(1, 0.1 * inch))

    # Sector drift table
    sector_headers = ["Sector", "Actual %", "Target %", "Drift", "Status"]
    sector_rows = [sector_headers]
    for sector, d in sorted(portfolio["sector_drift"].items()):
        if d["target"] == 0 and d["actual"] == 0:
            continue
        status = d["status"]
        status_color = (
            RED if status == "OVERWEIGHT" else
            ORANGE if status == "UNDERWEIGHT" else
            GREEN
        )
        drift_str = _format_pct(d["drift"])
        sector_rows.append([
            sector,
            f"{d['actual']:.1f}%",
            f"{d['target']:.1f}%",
            Paragraph(f"<font color='#{status_color.hexval()[2:]}'><b>{drift_str}</b></font>", styles["body"]),
            Paragraph(f"<font color='#{status_color.hexval()[2:]}'><b>{status}</b></font>", styles["body"])
        ])

    sector_tbl = Table(sector_rows, colWidths=[2.0*inch, 0.85*inch, 0.85*inch, 0.85*inch, 1.5*inch])
    sector_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("BOX", (0, 0), (-1, -1), 1, NAVY),
    ]))
    story.append(sector_tbl)
    story.append(PageBreak())

    # ── Holdings Table ─────────────────────────────────────────────────────────
    story.append(Paragraph("Current Portfolio Holdings (49 Positions + Money Market)", styles["h1"]))

    # Money market row
    mmkt_val = portfolio.get("mmkt_value", 0)
    story.append(Paragraph(
        f"<i>Money Market (10% target): {_format_currency(mmkt_val)} — not shown in table below</i>",
        styles["caption"]
    ))
    story.append(Spacer(1, 0.05 * inch))

    hold_headers = ["Symbol", "Name", "Sector", "Shares", "Price", "Mkt Value", "Gain/Loss", "Holding", "Analyst"]
    hold_rows = [hold_headers]
    positions = portfolio.get("positions", portfolio.get("holdings", []))
    for h in sorted(positions, key=lambda x: -x.get("market_value", 0)):
        gain = h.get("unrealized_gain", 0)
        gain_pct = h.get("gain_pct", 0)
        gain_str = _format_currency(gain)
        gain_pct_str = _format_pct(gain_pct)
        consensus = h.get("recommendation", h.get("analyst_consensus", "Hold"))
        cons_color = _consensus_color(consensus)
        lt_shares = h.get("lt_shares", h.get("shares", 0))
        total_shares = h.get("shares", 0)
        holding_tag = "LT" if lt_shares == total_shares else ("ST" if lt_shares == 0 else "Mixed")
        tag_color = "#16a34a" if holding_tag == "LT" else ("#ea580c" if holding_tag == "ST" else "#d97706")
        hold_rows.append([
            Paragraph(f"<b>{h.get('ticker', h.get('symbol',''))}</b>", styles["body"]),
            Paragraph(h.get("name", "")[:22], styles["caption"]),
            Paragraph(h.get("sector", "")[:18], styles["caption"]),
            f"{total_shares:,}",
            f"${h.get('price', h.get('current_price', 0)):,.2f}",
            f"${h.get('market_value', 0):,.0f}",
            Paragraph(
                f"<font color='{'#16a34a' if gain >= 0 else '#dc2626'}'>"
                f"<b>{gain_str} {gain_pct_str}</b></font>",
                styles["body"]
            ),
            Paragraph(
                f"<font color='{tag_color}'><b>{holding_tag}</b></font>",
                styles["body"]
            ),
            Paragraph(
                f"<font color='#{cons_color.hexval()[2:]}'><b>{consensus}</b></font>",
                styles["body"]
            )
        ])

    hold_tbl = Table(hold_rows,
                     colWidths=[0.55*inch, 1.65*inch, 1.3*inch, 0.5*inch,
                                 0.7*inch, 0.75*inch, 0.75*inch, 0.45*inch, 0.85*inch])
    hold_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("ALIGN", (3, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("BOX", (0, 0), (-1, -1), 1, NAVY),
    ]))
    story.append(hold_tbl)
    story.append(PageBreak())

    # ── AI Trading Plan ─────────────────────────────────────────────────────────
    story.append(Paragraph("AI-Generated Trading Plan", styles["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=8))

    # Sells
    sells = trading_plan.get("recommended_sells", [])
    if sells:
        story.append(Paragraph("Recommended Sells", styles["h2"]))
        sell_headers = ["Symbol", "Shares", "Proceeds", "Tax Impact", "Rationale", "Priority"]
        sell_rows = [sell_headers]
        for s in sells:
            pri = s.get("priority", "MEDIUM")
            pri_color = RED if pri == "HIGH" else ORANGE if pri == "MEDIUM" else GRAY
            sell_rows.append([
                Paragraph(f"<b>{s.get('symbol','')}</b>", styles["body"]),
                str(s.get("shares", "")),
                _format_currency(s.get("estimated_proceeds", 0)),
                Paragraph(s.get("tax_recommendation", s.get("tax_impact", "—"))[:60], styles["caption"]),
                Paragraph(s.get("rationale", "")[:100], styles["caption"]),
                Paragraph(f"<font color='#{pri_color.hexval()[2:]}'><b>{pri}</b></font>", styles["body"])
            ])
        sell_tbl = Table(sell_rows, colWidths=[0.65*inch, 0.55*inch, 0.8*inch, 1.5*inch, 2.5*inch, 0.6*inch])
        sell_tbl.setStyle(_trade_table_style())
        story.append(sell_tbl)
        story.append(Spacer(1, 0.12 * inch))

    # Buys
    buys = trading_plan.get("recommended_buys", [])
    if buys:
        story.append(Paragraph("Recommended Buys", styles["h2"]))
        buy_headers = ["Symbol", "Shares", "Est. Cost", "Sector", "Rationale", "Priority"]
        buy_rows = [buy_headers]
        for b in buys:
            pri = b.get("priority", "MEDIUM")
            pri_color = GREEN if pri == "HIGH" else BLUE if pri == "MEDIUM" else GRAY
            buy_rows.append([
                Paragraph(f"<b>{b.get('symbol','')}</b>", styles["body"]),
                str(b.get("shares", "")),
                _format_currency(b.get("estimated_cost", 0)),
                Paragraph(b.get("sector", "")[:18], styles["caption"]),
                Paragraph(b.get("rationale", "")[:100], styles["caption"]),
                Paragraph(f"<font color='#{pri_color.hexval()[2:]}'><b>{pri}</b></font>", styles["body"])
            ])
        buy_tbl = Table(buy_rows, colWidths=[0.65*inch, 0.55*inch, 0.8*inch, 1.1*inch, 2.9*inch, 0.6*inch])
        buy_tbl.setStyle(_trade_table_style(header_color=GREEN))
        story.append(buy_tbl)
        story.append(Spacer(1, 0.12 * inch))

    # Tax-loss harvesting
    harvesting = trading_plan.get("tax_loss_harvesting", [])
    if harvesting:
        story.append(Paragraph("Tax-Loss Harvesting Opportunities", styles["h2"]))
        tlh_headers = ["Symbol", "Action", "Tax Benefit", "Notes"]
        tlh_rows = [tlh_headers]
        for t in harvesting:
            tlh_rows.append([
                Paragraph(f"<b>{t.get('symbol','')}</b>", styles["body"]),
                t.get("action", ""),
                f"${t.get('tax_benefit', 0):,.0f}",
                Paragraph(t.get("notes", "")[:120], styles["caption"])
            ])
        tlh_tbl = Table(tlh_rows, colWidths=[0.7*inch, 1.0*inch, 0.9*inch, 4.0*inch])
        tlh_tbl.setStyle(_trade_table_style(header_color=GOLD))
        story.append(tlh_tbl)
        story.append(Spacer(1, 0.12 * inch))

    # ── Narrative ─────────────────────────────────────────────────────────────
    narrative = trading_plan.get("trading_plan_narrative", "")
    if narrative:
        story.append(PageBreak())
        story.append(Paragraph("Trading Plan Narrative & Rationale", styles["h1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=8))
        for para in narrative.split("\n\n"):
            para = para.strip()
            if para:
                if para.startswith("**") or para.isupper():
                    story.append(Paragraph(para.strip("*"), styles["h2"]))
                else:
                    story.append(Paragraph(para, styles["body_justify"]))

    # ── Risk Considerations ────────────────────────────────────────────────────
    risks = trading_plan.get("risk_considerations", [])
    if risks:
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph("Risk Considerations", styles["h2"]))
        for r in risks:
            story.append(Paragraph(f"• {r}", styles["body"]))

    # ── Summary Footer Box ────────────────────────────────────────────────────
    story.append(Spacer(1, 0.15 * inch))
    total_trades = trading_plan.get("total_estimated_trades", len(sells) + len(buys))
    net_tax = trading_plan.get("net_tax_impact", "See individual trade analysis")
    improvement = trading_plan.get("expected_portfolio_improvement", "—")

    summary_data = [
        ["Total Recommended Trades", "Estimated Net Tax Impact", "Expected Improvement"],
        [str(total_trades), net_tax, improvement]
    ]
    summary_tbl = Table(summary_data, colWidths=[2.2*inch, 2.2*inch, 2.2*inch])
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT_BLUE),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 1.5, NAVY),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, MID_GRAY),
    ]))
    story.append(summary_tbl)

    # ── Disclaimer ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.12 * inch))
    disclaimer = (
        "<i>This report was generated by an AI agent powered by Claude (Anthropic). "
        "It is intended as a decision-support tool only. All trades require review and approval "
        "by a licensed financial professional. This is not financial advice. Past performance "
        "is not indicative of future results. Tax estimates are approximations — consult your "
        "tax advisor before executing any transactions.</i>"
    )
    story.append(Paragraph(disclaimer, styles["caption"]))

    # Build PDF
    doc.build(story, onFirstPage=make_page_header_footer, onLaterPages=make_page_header_footer)
    return buffer.getvalue()


def _build_metric(label: str, value: str, styles: dict, color=None) -> Table:
    """Build a metric cell (label + big value)."""
    val_style = ParagraphStyle(
        "mv", fontSize=15, textColor=color or NAVY,
        fontName="Helvetica-Bold", spaceAfter=0
    )
    lbl_style = ParagraphStyle(
        "ml", fontSize=7.5, textColor=GRAY,
        fontName="Helvetica", spaceAfter=2
    )
    t = Table(
        [[Paragraph(label, lbl_style)], [Paragraph(value, val_style)]],
        colWidths=[1.45 * inch]
    )
    return t


def _trade_table_style(header_color=None):
    hc = header_color or NAVY
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), hc),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (2, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("BOX", (0, 0), (-1, -1), 1, NAVY),
    ])
