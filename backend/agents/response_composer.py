"""
Response Composer.

Assembles the final natural-language response from agent outputs.
Template-based (no LLM call) — all the intelligent content was produced
upstream. This saves 1 LLM call per request.

Improvement: richer response with growth metrics and chart counts.
"""
from __future__ import annotations

from datetime import datetime

from core.state import AgentState


async def response_composer_node(state: AgentState) -> AgentState:
    """
    LangGraph node: builds the final_response markdown string.
    """
    parts = []

    # Primary answer based on SQL results
    if state.sql_result:
        if state.sql_result.execution_error:
            parts.append(
                f"⚠️ **Query Error**: I was unable to retrieve the data. "
                f"*{state.sql_result.execution_error}*\n\n"
                "Please try rephrasing your question."
            )
        elif state.sql_result.awaiting_approval:
            parts.append(
                "⚠️ **Approval Required**: The generated SQL query has a confidence score below "
                "the safety threshold. Please review and approve it before execution."
            )
        elif state.sql_result.data is not None:
            row_count = state.sql_result.row_count
            if row_count == 0:
                parts.append("No data was found matching your query. Try adjusting the date range or filters.")
            else:
                parts.append(f"Here are the results for **{state.user_message}**:\n")

                # Summary statistics
                if state.analysis and state.analysis.kpis:
                    kpi_highlights = []
                    for key, val in state.analysis.kpis.items():
                        if "total" in key:
                            label = key.replace("total_", "").replace("_", " ").title()
                            formatted = f"${val:,.0f}" if isinstance(val, float) and "revenue" in key.lower() else f"{val:,.2f}" if isinstance(val, float) else str(val)
                            kpi_highlights.append(f"**{label}**: {formatted}")
                    if kpi_highlights:
                        parts.append(" · ".join(kpi_highlights[:4]))
                        parts.append("")

                # Growth highlights
                if state.analysis and state.analysis.growth_rates:
                    gr = state.analysis.growth_rates
                    if "mom_growth_pct" in gr:
                        direction = "📈" if gr["mom_growth_pct"] > 0 else "📉"
                        parts.append(f"{direction} Period-over-period change: **{gr['mom_growth_pct']:+.1f}%**")
                    if "overall_growth_pct" in gr:
                        direction = "📈" if gr["overall_growth_pct"] > 0 else "📉"
                        parts.append(f"{direction} Overall trend: **{gr['overall_growth_pct']:+.1f}%**")

                # Outlier highlights
                if state.analysis and state.analysis.outliers:
                    parts.append(f"\n⚡ **{len(state.analysis.outliers)} anomalies detected** in the data.")

                # Charts info
                if state.charts:
                    parts.append(f"\n📊 {len(state.charts)} visualization{'s' if len(state.charts) > 1 else ''} generated.")

                # Row count note
                parts.append(f"\n*Analysed {row_count:,} records.*")

    elif state.final_response:
        # Clarification or error set by orchestrator
        parts.append(state.final_response)

    else:
        parts.append("I wasn't able to process your request. Please try again.")

    state.final_response = "\n".join(parts)
    state.completed_at = datetime.utcnow()
    state.agent_trace.append("response_composer")
    return state
