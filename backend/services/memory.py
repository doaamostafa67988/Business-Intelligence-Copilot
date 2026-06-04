"""
Memory Service.

Manages conversational memory across turns:
- Load session from PostgreSQL
- Save updated state back to session
- Extract + persist named entities for reference resolution
- Summarise context every 5 turns to avoid token bloat

Improvement: added entity extraction and context summarisation.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.state import AgentState, ConversationMemory, ConversationTurn
from db.models import ConversationSession


async def load_memory(session_id: str, db: AsyncSession) -> ConversationMemory:
    """Load conversation memory from the database."""
    result = await db.execute(
        select(ConversationSession).where(ConversationSession.id == session_id)
    )
    session_row = result.scalar_one_or_none()

    if not session_row:
        return ConversationMemory(session_id=session_id)

    turns = [ConversationTurn(**t) for t in (session_row.turns or [])]
    return ConversationMemory(
        session_id=session_id,
        turns=turns,
        context_summary=session_row.context_summary or "",
        last_sql_result_snapshot=session_row.last_sql_snapshot,
        last_entities=session_row.last_entities or {},
        created_at=session_row.created_at,
        updated_at=session_row.updated_at,
    )


async def save_memory(
    session_id: str,
    state: AgentState,
    db: AsyncSession,
) -> None:
    """Persist updated conversation state to the database."""
    result = await db.execute(
        select(ConversationSession).where(ConversationSession.id == session_id)
    )
    session_row = result.scalar_one_or_none()

    # Extract entities from this turn
    entities = _extract_entities(state)

    # Add this turn to history
    new_turns_raw = list(state.conversation_history)
    new_turns_raw.append({
        "role": "user",
        "content": state.user_message,
        "entities": entities,
        "timestamp": datetime.utcnow().isoformat(),
    })
    new_turns_raw.append({
        "role": "assistant",
        "content": state.final_response,
        "entities": entities,
        "timestamp": datetime.utcnow().isoformat(),
    })

    # Summarise if too many turns
    context_summary = ""
    if len(new_turns_raw) > 10:
        context_summary = _summarise_context(new_turns_raw)
        # Keep only last 6 turns to stay within context window
        new_turns_raw = new_turns_raw[-6:]

    sql_snapshot = None
    if state.sql_result and state.sql_result.data:
        sql_snapshot = {
            "sql": state.sql_result.sql,
            "columns": state.sql_result.columns,
            "row_count": state.sql_result.row_count,
        }

    if session_row:
        session_row.turns = new_turns_raw
        session_row.context_summary = context_summary or session_row.context_summary
        session_row.last_entities = entities
        session_row.last_sql_snapshot = sql_snapshot
        session_row.updated_at = datetime.utcnow()
        db.add(session_row)
    else:
        new_session = ConversationSession(
            id=session_id,
            turns=new_turns_raw,
            context_summary=context_summary,
            last_entities=entities,
            last_sql_snapshot=sql_snapshot,
        )
        db.add(new_session)

    await db.commit()


def _extract_entities(state: AgentState) -> Dict[str, Any]:
    """
    Extract named entities from the current turn for reference resolution.
    E.g. {"region": "North", "metric": "revenue", "period": "Q4 2025"}
    """
    entities: Dict[str, Any] = {}

    if state.parsed_query:
        pq = state.parsed_query
        if pq.filters:
            entities.update(pq.filters)
        if pq.metric:
            entities["metric"] = pq.metric
        if pq.date_range:
            entities["period"] = pq.date_range
        if pq.dimensions:
            entities["dimensions"] = pq.dimensions

    return entities


def _summarise_context(turns: List[Dict]) -> str:
    """
    Build a compact context summary from conversation history.
    This is injected into prompts when session is long.
    """
    lines = []
    for turn in turns[-10:]:
        role = turn.get("role", "")
        content = turn.get("content", "")[:100]
        lines.append(f"{role.upper()}: {content}")
    return " | ".join(lines)


def build_history_for_state(memory: ConversationMemory) -> List[Dict[str, Any]]:
    """Convert ConversationMemory into the format AgentState.conversation_history expects."""
    history = []
    if memory.context_summary:
        history.append({
            "role": "system",
            "content": f"Previous context: {memory.context_summary}",
        })
    for turn in memory.turns[-6:]:
        history.append({
            "role": turn.role,
            "content": turn.content,
            "entities": turn.entities,
        })
    return history
