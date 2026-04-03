from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from utils import dependency as dependencies
from utils.logger import get_logger, log_event, log_exception
from schemas.llm_providers import LLMProviderChatRequest, ALLOWED_LLM_PROVIDERS
from schemas.model import LlmProvider
from services import chat_memory_service, llm_service
from utils.config import (
    LLM_CHAT_MEMORY_READ_LIMIT_DEFAULT,
    LLM_CHAT_MEMORY_READ_LIMIT_MAX,
)


router = APIRouter(prefix="", tags=["chat"])
_LOGGER = get_logger("api.routers.chat")


def _normalize_provider_name(value: str) -> str:
    return (value or "").strip().lower().replace(" ", "_")


def _get_provider_or_404(db: Session, llm_provider_id: int) -> LlmProvider:
    provider = db.query(LlmProvider).filter(LlmProvider.id == llm_provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="LLM provider not found")
    return provider


@router.get("/chat/{llm_provider_id}/memory")
def read_chat_memory(
    llm_provider_id: int,
    conversation_id: str | None = None,
    session_id: str | None = None,
    limit: int = Query(default=LLM_CHAT_MEMORY_READ_LIMIT_DEFAULT, ge=1, le=LLM_CHAT_MEMORY_READ_LIMIT_MAX),
):
    chat_memory_service.require_memory_scope(conversation_id, session_id)
    log_event(
        _LOGGER,
        20,
        "chat.memory.read.start",
        "Reading chat memory",
        llm_provider_id=llm_provider_id,
        conversation_id=conversation_id,
        session_id=session_id,
        limit=limit,
    )

    with dependencies.db_session() as db:
        provider = _get_provider_or_404(db, llm_provider_id)
        rows = chat_memory_service.read_memory_rows(db, llm_provider_id, conversation_id, session_id, limit)
        log_event(
            _LOGGER,
            20,
            "chat.memory.read.completed",
            "Read chat memory",
            provider_id=provider.id,
            provider=provider.provider,
            conversation_id=conversation_id,
            session_id=session_id,
            memory_count=len(rows),
            limit=limit,
        )
        return {
            "provider_id": provider.id,
            "provider": provider.provider,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "memory_count": len(rows),
            "limit": limit,
            "max_stored_turns": chat_memory_service.get_max_turns(),
            "memory": chat_memory_service.serialize_memory_rows(rows),
        }


@router.get("/chat/{llm_provider_id}/memory/summary")
def read_chat_memory_summary(
    llm_provider_id: int,
    conversation_id: str | None = None,
    session_id: str | None = None,
):
    chat_memory_service.require_memory_scope(conversation_id, session_id)
    log_event(
        _LOGGER,
        20,
        "chat.summary.read.start",
        "Reading chat memory summary",
        llm_provider_id=llm_provider_id,
        conversation_id=conversation_id,
        session_id=session_id,
    )

    with dependencies.db_session() as db:
        provider = _get_provider_or_404(db, llm_provider_id)
        summary = chat_memory_service.get_summary(db, llm_provider_id, conversation_id, session_id)
        log_event(
            _LOGGER,
            20,
            "chat.summary.read.completed",
            "Read chat memory summary",
            provider_id=provider.id,
            provider=provider.provider,
            conversation_id=conversation_id,
            session_id=session_id,
            has_summary=bool(summary),
            source=(summary.source if summary else None),
        )
        return {
            "provider_id": provider.id,
            "provider": provider.provider,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "summary": chat_memory_service.serialize_summary(summary),
        }


@router.post("/chat/memory/prune")
def prune_chat_memory(
    older_than_hours: int = Query(default=chat_memory_service.get_default_ttl_hours(), ge=1, le=24 * 365),
    llm_provider_id: int | None = None,
):
    with dependencies.db_session() as db:
        if llm_provider_id is not None:
            _get_provider_or_404(db, llm_provider_id)

        removed_memory_count, removed_summary_count = chat_memory_service.prune_expired_memory(
            db, older_than_hours, llm_provider_id
        )
        db.commit()

        log_event(
            _LOGGER,
            20,
            "chat.memory.pruned",
            "Pruned expired chat memory",
            llm_provider_id=llm_provider_id,
            older_than_hours=older_than_hours,
            removed_memory_count=removed_memory_count,
            removed_summary_count=removed_summary_count,
        )
        return {
            "older_than_hours": older_than_hours,
            "llm_provider_id": llm_provider_id,
            "removed_memory_count": removed_memory_count,
            "removed_summary_count": removed_summary_count,
        }


@router.post("/chat/{llm_provider_id}/memory/summary/regenerate")
def regenerate_chat_memory_summary(
    llm_provider_id: int,
    conversation_id: str | None = None,
    session_id: str | None = None,
):
    chat_memory_service.require_memory_scope(conversation_id, session_id)

    with dependencies.db_session() as db:
        provider = _get_provider_or_404(db, llm_provider_id)
        summary = chat_memory_service.force_refresh_summary(db, provider, conversation_id, session_id)
        db.commit()

        log_event(
            _LOGGER,
            20,
            "chat.summary.regenerated",
            "Forced summary regeneration",
            provider_id=provider.id,
            provider=provider.provider,
            conversation_id=conversation_id,
            session_id=session_id,
            source=(summary.source if summary else None),
        )
        return {
            "provider_id": provider.id,
            "provider": provider.provider,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "summary": chat_memory_service.serialize_summary(summary),
        }


@router.post("/chat/{llm_provider_id}")
def chat_with_provider(llm_provider_id: int, body: LLMProviderChatRequest):
    with dependencies.db_session() as db:
        provider = _get_provider_or_404(db, llm_provider_id)

        if provider.provider not in ALLOWED_LLM_PROVIDERS:
            raise HTTPException(status_code=400, detail="LLM provider not supported")

        requested_provider = _normalize_provider_name(body.provider_name)
        if requested_provider and requested_provider != provider.provider:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Request provider_name does not match provider id. "
                    f"requested='{requested_provider}', actual='{provider.provider}'"
                ),
            )

        persisted_memory = chat_memory_service.load_persisted_memory(db, provider.id, body)
        request_body = body.model_copy(
            update={
                "short_term_memory": [*persisted_memory, *body.short_term_memory],
            }
        )

        user_message = request_body.latest_user_message()
        try:
            chat_response = llm_service._chat_with_provider(provider, request_body)

            assistant_reply = ""
            if isinstance(chat_response, dict):
                assistant_reply = str(chat_response.get("reply", "") or "")

            pruned_count, summary = chat_memory_service.persist_chat_turn(
                db, provider, body, user_message, assistant_reply
            )
            db.commit()

            log_event(
                _LOGGER,
                20,
                "chat.message.sent",
                "Sent message to LLM provider",
                provider_id=provider.id,
                provider=provider.provider,
                conversation_id=request_body.conversation_id,
                session_id=request_body.session_id,
                request_id=request_body.request_id,
                persisted_memory_count=len(persisted_memory),
                pruned_memory_count=pruned_count,
                summary_source=(summary.source if summary else None),
                user_message_preview=user_message[:120],
            )
            return {"response": chat_response}
        except HTTPException as exc:
            db.rollback()
            log_event(
                _LOGGER,
                40,
                "chat.message.failed",
                "LLM provider request failed",
                provider_id=provider.id,
                provider=provider.provider,
                status_code=exc.status_code,
                detail=str(exc.detail),
                conversation_id=request_body.conversation_id,
                session_id=request_body.session_id,
                request_id=request_body.request_id,
            )
            raise
        except Exception as exc:
            db.rollback()
            log_exception(
                _LOGGER,
                "chat.message.unhandled_error",
                "Unexpected error while calling LLM provider",
                provider_id=provider.id,
                provider=provider.provider,
                error=str(exc),
                conversation_id=request_body.conversation_id,
                session_id=request_body.session_id,
                request_id=request_body.request_id,
            )
            raise HTTPException(status_code=500, detail="Unexpected chat routing error")