from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from schemas.llm_providers import LLMProviderChatRequest, LLMChatMessage
from schemas.model import LLMChatMemory, LLMChatSummary, LlmProvider
from services import llm_service
from utils.config import (
    LLM_CHAT_MEMORY_MAX_TURNS,
    LLM_CHAT_MEMORY_SUMMARIZATION_ENABLED,
    LLM_CHAT_MEMORY_SUMMARIZATION_TRIGGER_TURNS,
    LLM_CHAT_MEMORY_SUMMARY_INPUT_MAX_MESSAGES,
    LLM_CHAT_MEMORY_TTL_HOURS,
)


_ALLOWED_MEMORY_ROLES = {"system", "user", "assistant"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def require_memory_scope(conversation_id: str | None, session_id: str | None) -> None:
    if not (conversation_id or session_id):
        raise HTTPException(status_code=400, detail="conversation_id or session_id is required")


def build_memory_query(db: Session, provider_id: int, conversation_id: str | None, session_id: str | None):
    query = db.query(LLMChatMemory).filter(LLMChatMemory.llm_provider_id == provider_id)

    if conversation_id and session_id:
        query = query.filter(
            LLMChatMemory.conversation_id == conversation_id,
            LLMChatMemory.session_id == session_id,
        )
    elif conversation_id:
        query = query.filter(LLMChatMemory.conversation_id == conversation_id)
    elif session_id:
        query = query.filter(LLMChatMemory.session_id == session_id)

    return query


def build_summary_query(db: Session, provider_id: int, conversation_id: str | None, session_id: str | None):
    query = db.query(LLMChatSummary).filter(LLMChatSummary.llm_provider_id == provider_id)

    if conversation_id and session_id:
        query = query.filter(
            LLMChatSummary.conversation_id == conversation_id,
            LLMChatSummary.session_id == session_id,
        )
    elif conversation_id:
        query = query.filter(LLMChatSummary.conversation_id == conversation_id)
    elif session_id:
        query = query.filter(LLMChatSummary.session_id == session_id)

    return query


def read_memory_rows(db: Session, provider_id: int, conversation_id: str | None, session_id: str | None, limit: int) -> list[LLMChatMemory]:
    require_memory_scope(conversation_id, session_id)
    rows = (
        build_memory_query(db, provider_id, conversation_id, session_id)
        .order_by(LLMChatMemory.created_at.desc(), LLMChatMemory.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))


def load_persisted_memory(db: Session, provider_id: int, body: LLMProviderChatRequest, max_rows: int = 400) -> list[LLMChatMessage]:
    if not (body.conversation_id or body.session_id):
        return []

    rows = read_memory_rows(db, provider_id, body.conversation_id, body.session_id, max_rows)
    memory: list[LLMChatMessage] = []
    for row in rows:
        role = (row.role or "").strip().lower()
        if role not in _ALLOWED_MEMORY_ROLES:
            continue
        content = (row.content or "").strip()
        if not content:
            continue
        memory.append(LLMChatMessage(role=role, content=content))
    return memory


def serialize_memory_rows(rows: list[LLMChatMemory]) -> list[dict]:
    return [
        {
            "id": row.id,
            "llm_provider_id": row.llm_provider_id,
            "conversation_id": row.conversation_id,
            "session_id": row.session_id,
            "request_id": row.request_id,
            "role": row.role,
            "content": row.content,
            "created_at": to_utc_iso(row.created_at),
        }
        for row in rows
    ]


def serialize_summary(summary: LLMChatSummary | None) -> dict | None:
    if summary is None:
        return None
    return {
        "id": summary.id,
        "llm_provider_id": summary.llm_provider_id,
        "conversation_id": summary.conversation_id,
        "session_id": summary.session_id,
        "summary_text": summary.summary_text,
        "source": summary.source,
        "memory_count": summary.memory_count,
        "created_at": to_utc_iso(summary.created_at),
        "updated_at": to_utc_iso(summary.updated_at),
    }


def get_summary(db: Session, provider_id: int, conversation_id: str | None, session_id: str | None) -> LLMChatSummary | None:
    require_memory_scope(conversation_id, session_id)
    return build_summary_query(db, provider_id, conversation_id, session_id).first()


def enforce_max_stored_turns(db: Session, provider_id: int, conversation_id: str | None, session_id: str | None) -> int:
    if not (conversation_id or session_id):
        return 0

    max_rows = max(1, int(LLM_CHAT_MEMORY_MAX_TURNS)) * 2
    rows = (
        build_memory_query(db, provider_id, conversation_id, session_id)
        .order_by(LLMChatMemory.created_at.desc(), LLMChatMemory.id.desc())
        .all()
    )
    if len(rows) <= max_rows:
        return 0

    rows_to_delete = rows[max_rows:]
    for row in rows_to_delete:
        db.delete(row)
    return len(rows_to_delete)


def prune_expired_memory(db: Session, older_than_hours: int, provider_id: int | None = None) -> tuple[int, int]:
    cutoff = utc_now() - timedelta(hours=max(1, older_than_hours))

    memory_query = db.query(LLMChatMemory).filter(LLMChatMemory.created_at < cutoff)
    summary_query = db.query(LLMChatSummary).filter(LLMChatSummary.updated_at < cutoff)

    if provider_id is not None:
        memory_query = memory_query.filter(LLMChatMemory.llm_provider_id == provider_id)
        summary_query = summary_query.filter(LLMChatSummary.llm_provider_id == provider_id)

    memory_rows = memory_query.all()
    summary_rows = summary_query.all()

    for row in memory_rows:
        db.delete(row)
    for row in summary_rows:
        db.delete(row)

    return len(memory_rows), len(summary_rows)


def _render_transcript(rows: list[LLMChatMemory]) -> str:
    parts: list[str] = []
    for row in rows[-LLM_CHAT_MEMORY_SUMMARY_INPUT_MAX_MESSAGES:]:
        role = (row.role or "").strip().lower() or "unknown"
        content = (row.content or "").strip()
        if not content:
            continue
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _build_fallback_summary(rows: list[LLMChatMemory]) -> str:
    if not rows:
        return "No conversation history available."

    recent = rows[-min(6, len(rows)):]
    snippets: list[str] = []
    for row in recent:
        role = (row.role or "").strip().lower()
        content = (row.content or "").strip()
        if role not in _ALLOWED_MEMORY_ROLES or not content:
            continue
        snippets.append(f"{role}: {content[:240]}")
    return "Recent conversation summary:\n" + "\n".join(snippets)


def _generate_summary_text(provider: LlmProvider, rows: list[LLMChatMemory]) -> tuple[str, str]:
    transcript = _render_transcript(rows)
    if not transcript:
        return "No conversation history available.", "fallback"

    if not LLM_CHAT_MEMORY_SUMMARIZATION_ENABLED:
        return _build_fallback_summary(rows), "fallback"

    summary_request = LLMProviderChatRequest(
        provider_name=provider.provider,
        message=(
            "Summarize this conversation for future context retention. Include user preferences,"
            " constraints, decisions, unresolved questions, and stable facts. Be concise and factual.\n\n"
            f"Conversation transcript:\n{transcript}"
        ),
        temperature=0.2,
        max_tokens=300,
    )

    try:
        summary_response = llm_service._chat_with_provider(provider, summary_request)
        summary_text = str(summary_response.get("reply", "") if isinstance(summary_response, dict) else "").strip()
        if summary_text:
            return summary_text[:4000], "llm"
    except Exception:
        pass

    return _build_fallback_summary(rows), "fallback"


def maybe_refresh_summary(db: Session, provider: LlmProvider, conversation_id: str | None, session_id: str | None) -> LLMChatSummary | None:
    if not (conversation_id or session_id):
        return None

    trigger_rows = max(1, int(LLM_CHAT_MEMORY_SUMMARIZATION_TRIGGER_TURNS)) * 2
    rows = (
        build_memory_query(db, provider.id, conversation_id, session_id)
        .order_by(LLMChatMemory.created_at.asc(), LLMChatMemory.id.asc())
        .all()
    )
    if len(rows) < trigger_rows:
        return build_summary_query(db, provider.id, conversation_id, session_id).first()

    existing = build_summary_query(db, provider.id, conversation_id, session_id).first()
    if existing is not None and len(rows) - existing.memory_count < 2:
        return existing

    summary_text, source = _generate_summary_text(provider, rows)
    if existing is None:
        existing = LLMChatSummary(
            llm_provider_id=provider.id,
            conversation_id=conversation_id,
            session_id=session_id,
            summary_text=summary_text,
            source=source,
            memory_count=len(rows),
        )
        db.add(existing)
    else:
        existing.summary_text = summary_text
        existing.source = source
        existing.memory_count = len(rows)

    db.flush()
    return existing


def persist_chat_turn(db: Session, provider: LlmProvider, body: LLMProviderChatRequest, user_message: str, assistant_reply: str) -> tuple[int, LLMChatSummary | None]:
    has_memory_key = bool(body.conversation_id or body.session_id)
    if not has_memory_key:
        return 0, None

    if not user_message.strip() and not assistant_reply.strip():
        return 0, None

    if user_message.strip():
        db.add(
            LLMChatMemory(
                llm_provider_id=provider.id,
                conversation_id=body.conversation_id,
                session_id=body.session_id,
                request_id=body.request_id,
                role="user",
                content=user_message.strip(),
            )
        )

    if assistant_reply.strip():
        db.add(
            LLMChatMemory(
                llm_provider_id=provider.id,
                conversation_id=body.conversation_id,
                session_id=body.session_id,
                request_id=body.request_id,
                role="assistant",
                content=assistant_reply.strip(),
            )
        )

    db.flush()
    pruned_count = enforce_max_stored_turns(db, provider.id, body.conversation_id, body.session_id)
    summary = maybe_refresh_summary(db, provider, body.conversation_id, body.session_id)
    return pruned_count, summary


def force_refresh_summary(
    db: Session,
    provider: LlmProvider,
    conversation_id: str | None,
    session_id: str | None,
) -> LLMChatSummary | None:
    """Unconditionally regenerate the summary for a scope, bypassing the turn threshold."""
    require_memory_scope(conversation_id, session_id)

    rows = (
        build_memory_query(db, provider.id, conversation_id, session_id)
        .order_by(LLMChatMemory.created_at.asc(), LLMChatMemory.id.asc())
        .all()
    )
    if not rows:
        return build_summary_query(db, provider.id, conversation_id, session_id).first()

    summary_text, source = _generate_summary_text(provider, rows)
    existing = build_summary_query(db, provider.id, conversation_id, session_id).first()
    if existing is None:
        existing = LLMChatSummary(
            llm_provider_id=provider.id,
            conversation_id=conversation_id,
            session_id=session_id,
            summary_text=summary_text,
            source=source,
            memory_count=len(rows),
        )
        db.add(existing)
    else:
        existing.summary_text = summary_text
        existing.source = source
        existing.memory_count = len(rows)

    db.flush()
    return existing


def get_default_ttl_hours() -> int:
    return LLM_CHAT_MEMORY_TTL_HOURS


def get_max_turns() -> int:
    return LLM_CHAT_MEMORY_MAX_TURNS
