import json
from fastapi import APIRouter, HTTPException
from schemas.model import LlmProvider
from schemas.llm_providers import LLMProviderUpsert
from utils import dependency as dependencies
from utils.secrets_manager import get_secrets_manager
from utils.logger import get_logger, log_event, log_exception
from services.llm_service import (
    _normalize_llm_provider,
    _validate_credentials_map,
    _serialize_llm_provider,
)

router = APIRouter(prefix="/llm-providers", tags=["llm-providers"])
_LOGGER = get_logger("api.routers.llm_providers")


@router.get("")
def list_providers():
    with dependencies.db_session() as db:
        providers = db.query(LlmProvider).order_by(LlmProvider.provider).all()
        return [_serialize_llm_provider(p) for p in providers]


@router.get("/{provider_id}")
def get_provider(provider_id: int):
    with dependencies.db_session() as db:
        provider = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="LLM provider not found")
        return _serialize_llm_provider(provider)


@router.post("", status_code=201)
def create_provider(body: LLMProviderUpsert):
    normalized = _normalize_llm_provider(body.provider_name)

    with dependencies.db_session() as db:
        existing = db.query(LlmProvider).filter(LlmProvider.provider == normalized).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"LLM provider '{normalized}' already exists. Use PUT to update.",
            )

        cleaned_creds = _validate_credentials_map(body.credentials)
        encrypted_credentials = None
        if cleaned_creds:
            encrypted_credentials = get_secrets_manager().encrypt(json.dumps(cleaned_creds))

        provider = LlmProvider(
            provider=normalized,
            description=body.description,
            endpoint=body.endpoint,
            encrypted_credentials=encrypted_credentials,
        )
        db.add(provider)
        db.commit()
        db.refresh(provider)

        log_event(
            _LOGGER,
            20,
            "llm_provider.created",
            "LLM provider created",
            provider_id=provider.id,
            provider=provider.provider,
        )
        return _serialize_llm_provider(provider)


@router.put("/{provider_id}")
def update_provider(provider_id: int, body: LLMProviderUpsert):
    normalized = _normalize_llm_provider(body.provider_name)

    with dependencies.db_session() as db:
        provider = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="LLM provider not found")

        # Reject if renaming to a name already taken by another record
        conflict = (
            db.query(LlmProvider)
            .filter(LlmProvider.provider == normalized, LlmProvider.id != provider_id)
            .first()
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Another LLM provider with name '{normalized}' already exists.",
            )

        provider.provider = normalized
        if body.description is not None:
            provider.description = body.description
        if body.endpoint is not None:
            provider.endpoint = body.endpoint

        if body.credentials is not None:
            cleaned_creds = _validate_credentials_map(body.credentials)
            if cleaned_creds:
                provider.encrypted_credentials = get_secrets_manager().encrypt(
                    json.dumps(cleaned_creds)
                )
            else:
                provider.encrypted_credentials = None

        db.commit()
        db.refresh(provider)

        log_event(
            _LOGGER,
            20,
            "llm_provider.updated",
            "LLM provider updated",
            provider_id=provider.id,
            provider=provider.provider,
        )
        return _serialize_llm_provider(provider)


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: int):
    with dependencies.db_session() as db:
        provider = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="LLM provider not found")

        provider_name = provider.provider
        db.delete(provider)
        db.commit()

        log_event(
            _LOGGER,
            20,
            "llm_provider.deleted",
            "LLM provider deleted",
            provider_id=provider_id,
            provider=provider_name,
        )
