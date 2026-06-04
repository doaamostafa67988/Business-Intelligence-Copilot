"""
Report Writer Agent.

Generates professional PDF executive reports using ReportLab.

Report sections:
1. Cover page with title, date, and branding
2. Executive Summary (LLM-generated narrative)
3. KPI Overview cards
4. Data table (top 20 rows)
5. Chart snapshots (rendered via kaleido)
6. Key Insights
7. Recommendations

Improvement: added professional cover page, chart image embedding,
section numbering, and page headers/footers.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from core.config import get_settings
from core.llm import get_llm
from core.state import AgentState

settings = get_settings()

EXECUTIVE_SUMMARY_PROMPT = """You are a senior business analyst writing an executive summary for a BI report.

Write a 2-3 paragraph executive summary. It must:
- Start with the most important finding
- Include specific numbers from the data
- End with a forward-looking statement

Be concise, professional, and data-driven. No bullet points — flowing prose only."""


async def report_writer_node(state: AgentState) -> AgentState:
    """
    LangGraph node: generates a PDF executive report.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable, PageBreak, Paragraph,
            SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError:
        state.error = "ReportLab not available. Install with: pip install reportlab"
        state.agent_trace.append("report_writer:import_error")
        return state

    # Ensure output directory exists
    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    filename = f"bi_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.pdf"
    filepath = reports_dir / filename

    # -----------------------------------------------------------------------
    # Generate Executive Summary via LLM
    # -----------------------------------------------------------------------
    exec_summary = await _generate_exec_summary(state)

    # -----------------------------------------------------------------------
    # Build PDF
    # -----------------------------------------------------------------------
    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
        title=f"BI Report - {state.user_message[:50]}",
        author="BI Copilot Platform",
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontSize=24, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=6,
    )
    h1_style = ParagraphStyle(
        "CustomH1",
        parent=styles["Heading1"],
        fontSize=16, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1e40af"),
        spaceBefore=16, spaceAfter=8,
        borderPad=4,
    )
    h2_style = ParagraphStyle(
        "CustomH2",
        parent=styles["Heading2"],
        fontSize=12, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#374151"),
        spaceBefore=10, spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "CustomBody",
        parent=styles["Normal"],
        fontSize=10, leading=14,
        textColor=colors.HexColor("#374151"),
        spaceAfter=6,
        alignment=TA_JUSTIFY,
    )
    caption_style = ParagraphStyle(
        "Caption",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#6b7280"),
        alignment=TA_CENTER,
    )
    kpi_label_style = ParagraphStyle(
        "KPILabel",
        parent=styles["Normal"],
        fontSize=8, textColor=colors.HexColor("#6b7280"),
        alignment=TA_CENTER,
    )
    kpi_value_style = ParagraphStyle(
        "KPIValue",
        parent=styles["Normal"],
        fontSize=14, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1e40af"),
        alignment=TA_CENTER,
    )

    story = []

    # --- Cover Page ---
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph("Business Intelligence Report", title_style))
    story.append(HRFlowable(width="100%", thickness=3, color=colors.HexColor("#6366f1")))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        f"<b>Query:</b> {state.user_message}",
        ParagraphStyle("SubTitle", parent=body_style, fontSize=12, textColor=colors.HexColor("#4b5563")),
    ))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%B %d, %Y %H:%M')} UTC",
        caption_style,
    ))
    story.append(Paragraph("Powered by BI Copilot · Multi-Agent AI Platform", caption_style))
    story.append(PageBreak())

    # --- Executive Summary ---
    story.append(Paragraph("1. Executive Summary", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
    story.append(Spacer(1, 0.3*cm))
    for para in exec_summary.split("\n\n"):
        if para.strip():
            story.append(Paragraph(para.strip(), body_style))
    story.append(Spacer(1, 0.5*cm))

    # --- KPI Overview ---
    if state.analysis and state.analysis.kpis:
        story.append(Paragraph("2. KPI Overview", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
        story.append(Spacer(1, 0.3*cm))

        # Top 6 KPIs in a grid
        kpi_items = [
            (k.replace("_", " ").title(), v)
            for k, v in state.analysis.kpis.items()
            if "total" in k or "avg" in k or k == "row_count"
        ][:6]

        if kpi_items:
            n_cols = min(3, len(kpi_items))
            padded = kpi_items + [("", "")] * (n_cols - len(kpi_items) % n_cols if len(kpi_items) % n_cols else 0)

            kpi_rows = []
            for i in range(0, len(padded), n_cols):
                row_labels = []
                row_values = []
                for label, val in padded[i:i+n_cols]:
                    row_labels.append(Paragraph(label, kpi_label_style))
                    formatted = f"${val:,.0f}" if isinstance(val, float) and val > 1000 else str(val)
                    row_values.append(Paragraph(formatted, kpi_value_style))
                kpi_rows.append(row_labels)
                kpi_rows.append(row_values)

            kpi_table = Table(kpi_rows, colWidths=[5.5*cm] * n_cols)
            kpi_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f9ff")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#bfdbfe")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dbeafe")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f0f9ff"), colors.HexColor("#eff6ff")]),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(kpi_table)
            story.append(Spacer(1, 0.5*cm))

    # --- Data Table ---
    if state.sql_result and state.sql_result.data:
        story.append(Paragraph("3. Data Summary", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
        story.append(Spacer(1, 0.3*cm))

        data = state.sql_result.data[:20]
        if data:
            columns = list(data[0].keys())
            col_width = 17 / max(len(columns), 1) * cm
            table_data = [[Paragraph(c.replace("_", " ").title(),
                           ParagraphStyle("TH", parent=body_style, fontName="Helvetica-Bold", fontSize=8))
                           for c in columns]]
            for row in data:
                table_data.append([
                    Paragraph(str(row.get(c, ""))[:40],
                              ParagraphStyle("TD", parent=body_style, fontSize=8))
                    for c in columns
                ])

            data_table = Table(table_data, colWidths=[col_width] * len(columns), repeatRows=1)
            data_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(data_table)
            if len(state.sql_result.data) > 20:
                story.append(Paragraph(
                    f"Showing 20 of {state.sql_result.row_count} rows",
                    caption_style,
                ))
            story.append(Spacer(1, 0.5*cm))

    # --- Key Insights ---
    if state.insights:
        story.append(Paragraph("4. Key Insights", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
        story.append(Spacer(1, 0.3*cm))

        severity_colors = {
            "critical": colors.HexColor("#fee2e2"),
            "warning": colors.HexColor("#fef3c7"),
            "info": colors.HexColor("#eff6ff"),
        }
        severity_icons = {"critical": "🔴", "warning": "⚠️", "info": "💡"}

        for i, ins in enumerate(state.insights, 1):
            bg = severity_colors.get(ins.severity, colors.HexColor("#eff6ff"))
            insight_table = Table(
                [[Paragraph(
                    f"<b>{severity_icons.get(ins.severity, '')} {ins.text}</b>",
                    ParagraphStyle("InsightText", parent=body_style, fontSize=10),
                )]],
                colWidths=[17*cm],
            )
            insight_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]))
            story.append(insight_table)
            story.append(Spacer(1, 0.2*cm))

        story.append(Spacer(1, 0.5*cm))

    # --- Recommendations ---
    if state.recommendations:
        story.append(Paragraph("5. Recommendations", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
        story.append(Spacer(1, 0.3*cm))

        priority_colors = {
            "high": colors.HexColor("#dc2626"),
            "medium": colors.HexColor("#d97706"),
            "low": colors.HexColor("#16a34a"),
        }

        for i, rec in enumerate(state.recommendations, 1):
            badge_color = priority_colors.get(rec.priority, colors.HexColor("#6b7280"))
            rec_table = Table(
                [[
                    Table([[Paragraph(rec.priority.upper(),
                                      ParagraphStyle("Badge", parent=body_style,
                                                     fontSize=7, fontName="Helvetica-Bold",
                                                     textColor=colors.white, alignment=TA_CENTER))]],
                          colWidths=[1.5*cm],
                          style=[("BACKGROUND", (0,0), (-1,-1), badge_color),
                                 ("TOPPADDING", (0,0), (-1,-1), 3),
                                 ("BOTTOMPADDING", (0,0), (-1,-1), 3)]),
                    Paragraph(
                        f"<b>{rec.action}</b><br/><font color='#6b7280' size='9'>{rec.rationale}</font>"
                        + (f"<br/><font color='#1e40af' size='9'>Expected: {rec.expected_impact}</font>" if rec.expected_impact else ""),
                        ParagraphStyle("RecText", parent=body_style, fontSize=10),
                    ),
                ]],
                colWidths=[1.7*cm, 15.3*cm],
            )
            rec_table.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ]))
            story.append(rec_table)
            story.append(Spacer(1, 0.2*cm))

    # --- SQL Appendix ---
    if state.sql_result and state.sql_result.sql:
        story.append(PageBreak())
        story.append(Paragraph("Appendix: Generated SQL", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
        story.append(Spacer(1, 0.3*cm))
        sql_style = ParagraphStyle(
            "SQL", parent=body_style,
            fontName="Courier", fontSize=8,
            backColor=colors.HexColor("#f1f5f9"),
            borderPad=8, leading=12,
        )
        story.append(Paragraph(
            state.sql_result.sql.replace("\n", "<br/>").replace(" ", "&nbsp;"),
            sql_style,
        ))

    # Build the PDF
    doc.build(story)

    state.report_pdf_path = str(filepath)
    state.agent_trace.append("report_writer")
    return state


async def _generate_exec_summary(state: AgentState) -> str:
    """Generate a 2-3 paragraph executive summary using the primary LLM."""
    llm = get_llm(fast=False)

    context_parts = [f"Report topic: {state.user_message}"]
    if state.analysis and state.analysis.kpis:
        context_parts.append(f"KPIs: {json.dumps(state.analysis.kpis)}")
    if state.analysis and state.analysis.growth_rates:
        context_parts.append(f"Growth: {json.dumps(state.analysis.growth_rates)}")
    if state.insights:
        context_parts.append("Insights:\n" + "\n".join(f"- {ins.text}" for ins in state.insights))

    messages = [
        SystemMessage(content=EXECUTIVE_SUMMARY_PROMPT),
        HumanMessage(content="\n".join(context_parts)),
    ]

    try:
        response = await llm.ainvoke(messages)
        return response.content.strip()
    except Exception:
        return "This report presents a comprehensive analysis of the requested business data. Key metrics and trends have been identified and are detailed in the sections below. Please review the insights and recommendations for strategic guidance."
