import json
from fastapi import APIRouter, HTTPException
from schemas.model import LlmProvider, LLMCredential
from schemas.llm_providers import LLMProviderUpsert
from utils import dependency as dependencies
from utils.secrets_manager import get_secrets_manager
from utils.logger import get_logger, log_event, log_exception
from services.llm_service import (
    _normalize_llm_provider,
    _validate_credentials_map,
    _serialize_llm_provider,
)
from schemas.llm_providers import LLM_PROVIDER_CREDENTIAL_TEMPLATES, ALLOWED_LLM_PROVIDERS


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
            raise HTTPException(status_code=409, detail="Provider already exists")

        # Create provider first
        provider = LlmProvider(
            provider=normalized,
            description=body.description,
            endpoint=body.endpoint,
            encrypted_credentials=None,
        )
        db.add(provider)
        db.flush()  # Get provider.id without committing

        # Now build credentials list with provider.id
        credential_list = []
        if body.credentials:
            allowed = set(LLM_PROVIDER_CREDENTIAL_TEMPLATES.get(normalized, []))
            for key, value in body.credentials.items():
                if key not in allowed:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid credential key '{key}' for provider '{normalized}'",
                    )
                if not isinstance(value, str) or not value.strip():
                    raise HTTPException(status_code=400, detail=f"Credential value for '{key}' must be non-empty string")
                
                encrypted_value = get_secrets_manager().encrypt(value)
                credential_list.append(
                    LLMCredential(
                        llm_provider_id=provider.id,
                        key_name=key,
                        encrypted_value=encrypted_value,
                    )
                )

        provider.credential = credential_list

        db.commit()
        db.refresh(provider)

        log_event(_LOGGER, 20, "llm_provider.created", "LLM provider created", provider_id=provider.id, provider=provider.provider)
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

        # Update credentials as child LLMCredential records
        if body.credentials is not None:
            allowed = set(LLM_PROVIDER_CREDENTIAL_TEMPLATES.get(normalized, []))
            
            # Clear existing credentials
            db.query(LLMCredential).filter(LLMCredential.llm_provider_id == provider_id).delete()
            
            # Add new credentials
            credential_list = []
            if body.credentials:
                for key, value in body.credentials.items():
                    if key not in allowed:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid credential key '{key}' for provider '{normalized}'",
                        )
                    if not isinstance(value, str) or not value.strip():
                        raise HTTPException(status_code=400, detail=f"Credential value for '{key}' must be non-empty string")
                    
                    encrypted_value = get_secrets_manager().encrypt(value)
                    credential_list.append(
                        LLMCredential(
                            llm_provider_id=provider_id,
                            key_name=key,
                            encrypted_value=encrypted_value,
                        )
                    )
            
            provider.credential = credential_list
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

