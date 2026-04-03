from fastapi import APIRouter
from schemas.llm_providers import LLMProviderUpsert
from utils import dependency as dependencies
from utils.logger import get_logger, log_event
from services.llm_service import (
    list_llm_providers,
    get_llm_provider_or_404,
    create_llm_provider,
    update_llm_provider,
    delete_llm_provider,
    _serialize_llm_provider,
    get_provided_models,
)


router = APIRouter(prefix="/llm-providers", tags=["llm-providers"])
_LOGGER = get_logger("api.routers.llm_providers")


@router.get("")
def list_providers():
    with dependencies.db_session() as db:
        providers = list_llm_providers(db)
        log_event(
            _LOGGER,
            20,
            "llm_provider.listed",
            "Listed LLM providers",
            provider_count=len(providers),
        )
        return [_serialize_llm_provider(p) for p in providers]


@router.get("/{provider_id}")
def get_provider(provider_id: int):
    with dependencies.db_session() as db:
        provider = get_llm_provider_or_404(db, provider_id)
        log_event(
            _LOGGER,
            20,
            "llm_provider.retrieved",
            "Retrieved LLM provider",
            provider_id=provider.id,
            provider=provider.provider,
        )
        return _serialize_llm_provider(provider)


@router.post("", status_code=201)
def create_provider(body: LLMProviderUpsert):
    with dependencies.db_session() as db:
        provider = create_llm_provider(db, body)

        log_event(_LOGGER, 20, "llm_provider.created", "LLM provider created", provider_id=provider.id, provider=provider.provider)
        return _serialize_llm_provider(provider)

@router.put("/{provider_id}")
def update_provider(provider_id: int, body: LLMProviderUpsert):
    with dependencies.db_session() as db:
        provider = update_llm_provider(db, provider_id, body)

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
        provider_name = delete_llm_provider(db, provider_id)

        log_event(
            _LOGGER,
            20,
            "llm_provider.deleted",
            "LLM provider deleted",
            provider_id=provider_id,
            provider=provider_name,
        )

@router.get("/{llm_provider_id}/models")
def get_provider_models(llm_provider_id: int):
    with dependencies.db_session() as db:
        models = get_provided_models(db, llm_provider_id)
        log_event(
            _LOGGER,
            20,
            "llm_provider.models.listed",
            "Listed provider models",
            provider_id=llm_provider_id,
            model_count=len(models.models),
        )
        return models   