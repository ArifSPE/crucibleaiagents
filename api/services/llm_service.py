import json
from urllib import request as urllib_request
from urllib import error as urllib_error
from typing import Dict, Any, Optional, List
from fastapi import HTTPException
from sqlalchemy.orm import Session
from schemas.model import LlmProvider, LLMCredential
from utils.secrets_manager import get_secrets_manager
from utils.config import ALLOWED_LLM_PROVIDERS
from utils.logger import get_logger, log_event, log_exception
from schemas.llm_providers import (
    LLMProviderChatRequest as LlmProviderChatRequest,
    LLMProviderUpsert,
    LLM_PROVIDER_CREDENTIAL_TEMPLATES,
    LLM_ModelsListResponse, LLM_Model
)

LOGGER = get_logger("api.services.llm_service")


def _normalize_llm_provider(provider: str) -> str:
    normalized = (provider or "").strip().lower().replace(" ", "_")
    if normalized not in ALLOWED_LLM_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported provider. Allowed values: "
                + ", ".join(sorted(ALLOWED_LLM_PROVIDERS))
            ),
        )
    return normalized


def _validate_credentials_map(credentials: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not credentials:
        return {}

    cleaned: Dict[str, str] = {}
    for raw_key, raw_value in credentials.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        value = "" if raw_value is None else str(raw_value)
        cleaned[key] = value
    return cleaned


def list_llm_providers(db: Session) -> List[LlmProvider]:
    return db.query(LlmProvider).order_by(LlmProvider.provider).all()


def get_llm_provider_or_404(db: Session, provider_id: int) -> LlmProvider:
    provider = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="LLM provider not found")
    return provider


def _build_child_credentials(normalized: str, credentials: Optional[Dict[str, str]], provider_id: int) -> List[LLMCredential]:
    credential_list: List[LLMCredential] = []
    if not credentials:
        return credential_list

    allowed = set(LLM_PROVIDER_CREDENTIAL_TEMPLATES.get(normalized, []))
    for key, value in credentials.items():
        if key not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid credential key '{key}' for provider '{normalized}'",
            )
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(
                status_code=400,
                detail=f"Credential value for '{key}' must be non-empty string",
            )
        encrypted_value = get_secrets_manager().encrypt(value)
        credential_list.append(
            LLMCredential(
                llm_provider_id=provider_id,
                key_name=key,
                encrypted_value=encrypted_value,
            )
        )
    return credential_list


def create_llm_provider(db: Session, body: LLMProviderUpsert) -> LlmProvider:
    normalized = _normalize_llm_provider(body.provider_name)
    existing = db.query(LlmProvider).filter(LlmProvider.provider == normalized).first()
    if existing:
        raise HTTPException(status_code=409, detail="Provider already exists")

    provider = LlmProvider(
        provider=normalized,
        description=body.description,
        endpoint=body.endpoint,
        encrypted_credentials=None,
    )
    db.add(provider)
    db.flush()

    provider.credential = _build_child_credentials(normalized, body.credentials, provider.id)

    db.commit()
    db.refresh(provider)
    return provider


def update_llm_provider(db: Session, provider_id: int, body: LLMProviderUpsert) -> LlmProvider:
    normalized = _normalize_llm_provider(body.provider_name)
    provider = get_llm_provider_or_404(db, provider_id)

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
        db.query(LLMCredential).filter(LLMCredential.llm_provider_id == provider_id).delete()
        provider.credential = _build_child_credentials(normalized, body.credentials, provider_id)
        provider.encrypted_credentials = None

    db.commit()
    db.refresh(provider)
    return provider


def delete_llm_provider(db: Session, provider_id: int) -> str:
    provider = get_llm_provider_or_404(db, provider_id)
    provider_name = provider.provider
    db.delete(provider)
    db.commit()
    return provider_name


def _serialize_llm_provider(db_provider: LlmProvider) -> Dict[str, Any]:
    from services.run_service import _to_utc_iso

    credential_keys: List[str] = []
    # Check for credentials in child LLMCredential records (primary storage)
    has_keys = bool(db_provider.credential and isinstance(db_provider.credential, list) and len(db_provider.credential) > 0)
    if has_keys:
        # Extract credential key names from child records
        credential_keys = sorted([cred.key_name for cred in db_provider.credential if cred and cred.key_name])
    # Fall back to encrypted_credentials field for backward compatibility
    has_credentials = has_keys or bool(db_provider.encrypted_credentials and str(db_provider.encrypted_credentials).strip())
    
    # Build credential list (decrypted values)
    list_of_credentials = []
    if has_keys:
        for cred in db_provider.credential:
            if cred and cred.key_name:
                try:
                    decrypted_value = get_secrets_manager().decrypt(cred.encrypted_value)
                    list_of_credentials.append({"key_name": cred.key_name})
                except Exception:
                    list_of_credentials.append({"key_name": cred.key_name})

    # Fall back to encrypted_credentials for backward compatibility
    if not has_keys and db_provider.encrypted_credentials:
        try:
            decrypted = get_secrets_manager().decrypt(db_provider.encrypted_credentials)
            parsed = json.loads(decrypted) if decrypted else {}
            if isinstance(parsed, dict):
                credential_keys = sorted([str(key) for key in parsed.keys() if str(key).strip()])
        except Exception:
            credential_keys = []


    return {
        "id": db_provider.id,
        "provider": db_provider.provider,
        "description": db_provider.description or "",
        "endpoint": db_provider.endpoint or "",
        "has_credentials": has_credentials,
        "credential_keys": credential_keys,
        "created_at": _to_utc_iso(db_provider.created_at),
        "updated_at": _to_utc_iso(db_provider.updated_at),
        "credential": list_of_credentials,
    }


def _decrypt_provider_credentials(db_provider: LlmProvider) -> Dict[str, str]:
    provider_id = db_provider.id
    # Primary: read from child LLMCredential records (current storage model)
    has_keys = bool(db_provider.credential and isinstance(db_provider.credential, list) and len(db_provider.credential) > 0)
    if has_keys:
        result: Dict[str, str] = {}
        for cred in db_provider.credential:
            if cred and cred.key_name:
                try:
                    decrypted_value = get_secrets_manager().decrypt(cred.encrypted_value)
                    result[str(cred.key_name)] = decrypted_value or ""
                except Exception:
                    log_event(
                        LOGGER,
                        30,
                        "llm.credentials.decrypt_failed",
                        "Failed to decrypt provider credential",
                        provider_id=provider_id,
                        key_name=cred.key_name,
                    )
                    result[str(cred.key_name)] = ""
        log_event(
            LOGGER,
            10,
            "llm.credentials.loaded",
            "Loaded provider credentials from child records",
            provider_id=provider_id,
            credential_count=len(result),
            source="child_records",
        )
        return result

    # Fallback: legacy encrypted_credentials field
    if not db_provider.encrypted_credentials or not str(db_provider.encrypted_credentials).strip():
        log_event(
            LOGGER,
            10,
            "llm.credentials.none",
            "No credentials found for provider",
            provider_id=provider_id,
        )
        return {}

    try:
        decrypted = get_secrets_manager().decrypt(db_provider.encrypted_credentials)
        parsed = json.loads(decrypted) if decrypted else {}
        if isinstance(parsed, dict):
            log_event(
                LOGGER,
                10,
                "llm.credentials.loaded",
                "Loaded provider credentials from legacy field",
                provider_id=provider_id,
                credential_count=len(parsed),
                source="legacy_field",
            )
            return {str(k): "" if v is None else str(v) for k, v in parsed.items()}
    except Exception:
        log_event(
            LOGGER,
            30,
            "llm.credentials.decrypt_failed",
            "Failed to decrypt legacy provider credentials",
            provider_id=provider_id,
            source="legacy_field",
        )
        return {}
    return {}


def _post_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None, timeout_seconds: int = 30) -> Dict[str, Any]:
    log_event(LOGGER, 10, "llm.http.post.start", "Posting request to provider", url=url, timeout_seconds=timeout_seconds)
    data = json.dumps(payload).encode("utf-8")
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if headers:
        request_headers.update(headers)

    req = urllib_request.Request(url=url, data=data, headers=request_headers, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
            log_event(LOGGER, 10, "llm.http.post.success", "Received provider response", url=url, status_code=200)
            return json.loads(body) if body else {}
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
        detail = body.strip() or f"Provider HTTP error: {exc.code}"
        log_event(
            LOGGER,
            40,
            "llm.http.post.failed",
            "Provider HTTP error",
            url=url,
            status_code=exc.code,
            detail=detail[:200],
        )
        raise HTTPException(status_code=502, detail=f"Provider request failed ({exc.code}): {detail[:400]}")
    except urllib_error.URLError as exc:
        log_event(LOGGER, 40, "llm.http.post.failed", "Provider connection failed", url=url, reason=str(exc.reason))
        raise HTTPException(status_code=502, detail=f"Provider connection failed: {exc.reason}")
    except Exception as exc:
        log_exception(LOGGER, "llm.http.post.unhandled_error", "Unexpected provider POST error", url=url, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Provider request failed: {exc}")


def _get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout_seconds: int = 30) -> Dict[str, Any]:
    log_event(LOGGER, 20, "llm.http.get.start", "Fetching provider resource", url=url, timeout_seconds=timeout_seconds)
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)

    req = urllib_request.Request(url=url, headers=request_headers, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body) if body else {}
            log_event(LOGGER, 20, "llm.http.get.success", "Fetched provider resource", url=url, status_code=200)
            return result
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
        detail = body.strip() or f"Provider HTTP error: {exc.code}"
        log_event(LOGGER, 40, "llm.http.get.failed", "Provider HTTP error", url=url, status_code=exc.code, detail=detail[:200])
        raise HTTPException(status_code=502, detail=f"Provider request failed ({exc.code}): {detail[:400]}")
    except urllib_error.URLError as exc:
        log_event(LOGGER, 40, "llm.http.get.failed", "Provider connection failed", url=url, reason=str(exc.reason))
        raise HTTPException(status_code=502, detail=f"Provider connection failed: {exc.reason}")
    except Exception as exc:
        log_exception(LOGGER, "llm.http.get.unhandled_error", "Unexpected provider GET error", url=url, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Provider request failed: {exc}")


def _normalize_endpoint(base_endpoint: str, default_endpoint: str) -> str:
    endpoint = (base_endpoint or "").strip() or default_endpoint
    return endpoint.rstrip("/")


def _resolve_model_name(chat_request: LlmProviderChatRequest, credentials: Dict[str, str], fallback: str) -> str:
    request_model = (chat_request.model or "").strip()
    if request_model:
        return request_model
    credential_model = (credentials.get("model") or "").strip()
    if credential_model:
        return credential_model
    return fallback


def _build_chat_messages(chat_request: LlmProviderChatRequest) -> List[Dict[str, str]]:
    return chat_request.build_messages()


def _chat_with_ollama(provider: LlmProvider, credentials: Dict[str, str], chat_request: LlmProviderChatRequest) -> Dict[str, Any]:
    model = _resolve_model_name(chat_request, credentials, "llama3.1")
    configured_endpoint = (provider.endpoint or credentials.get("endpoint", "")).strip()
    candidate_endpoints: List[str] = []

    if configured_endpoint:
        candidate_endpoints.append(configured_endpoint)

    # Support both local host execution and Dockerized execution without forcing users to reconfigure.
    for fallback in ["http://localhost:11434", "http://127.0.0.1:11434", "http://host.docker.internal:11434"]:
        if fallback not in candidate_endpoints:
            candidate_endpoints.append(fallback)

    payload: Dict[str, Any] = {
        "model": model,
        "messages": _build_chat_messages(chat_request),
        "stream": False,
    }
    if chat_request.temperature is not None:
        payload["options"] = {"temperature": chat_request.temperature}

    headers: Dict[str, str] = {}
    api_key = (credentials.get("api_key") or "").strip()
    if api_key and provider.provider != "local_ollama":
        headers["Authorization"] = f"Bearer {api_key}"

    errors: List[str] = []
    for raw_endpoint in candidate_endpoints:
        endpoint = _normalize_endpoint(raw_endpoint, "http://localhost:11434")
        url = f"{endpoint}/api/chat"
        try:
            response_json = _post_json(url, payload, headers=headers)
            message_obj = response_json.get("message", {}) if isinstance(response_json, dict) else {}
            reply = message_obj.get("content") if isinstance(message_obj, dict) else None
            if not reply:
                reply = str(response_json)[:2000]

            return {
                "provider_id": provider.id,
                "provider": provider.provider,
                "endpoint": endpoint,
                "model": model,
                "reply": reply,
            }
        except HTTPException as exc:
            errors.append(f"{endpoint}: {exc.detail}")

    raise HTTPException(
        status_code=502,
        detail="Ollama chat failed on all candidate endpoints: " + " | ".join(errors[:3]),
    )


def _chat_with_anthropic(provider: LlmProvider, credentials: Dict[str, str], chat_request: LlmProviderChatRequest) -> Dict[str, Any]:
    endpoint = _normalize_endpoint(provider.endpoint or credentials.get("endpoint", ""), "https://api.anthropic.com")
    model = _resolve_model_name(chat_request, credentials, "claude-3-5-sonnet-20241022")
    api_key = (credentials.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="Missing provider api_key for Anthropic/Claude")

    all_messages = _build_chat_messages(chat_request)
    system_chunks = [msg.get("content", "") for msg in all_messages if msg.get("role") == "system"]
    conversational_messages = [
        {"role": str(msg.get("role")), "content": str(msg.get("content", ""))}
        for msg in all_messages
        if msg.get("role") in {"user", "assistant"}
    ]

    if not conversational_messages:
        latest_user_message = chat_request.latest_user_message()
        if latest_user_message:
            conversational_messages = [{"role": "user", "content": latest_user_message}]

    url = f"{endpoint}/v1/messages"
    payload: Dict[str, Any] = {
        "model": model,
        "max_tokens": chat_request.max_tokens or 256,
        "messages": conversational_messages,
    }
    if system_chunks:
        payload["system"] = "\n\n".join([chunk for chunk in system_chunks if chunk][:4])
    if chat_request.temperature is not None:
        payload["temperature"] = chat_request.temperature

    response_json = _post_json(
        url,
        payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )

    reply = ""
    content = response_json.get("content", []) if isinstance(response_json, dict) else []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                reply += str(block.get("text", ""))

    if not reply:
        reply = str(response_json)[:2000]

    return {
        "provider_id": provider.id,
        "provider": provider.provider,
        "endpoint": endpoint,
        "model": model,
        "reply": reply,
    }


def _chat_openai_compatible(provider: LlmProvider, credentials: Dict[str, str], chat_request: LlmProviderChatRequest) -> Dict[str, Any]:
    endpoint = _normalize_endpoint(provider.endpoint or credentials.get("endpoint", ""), "")
    if not endpoint:
        raise HTTPException(status_code=400, detail="Endpoint is required for this provider")

    api_key = (credentials.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="Missing provider api_key")

    model = _resolve_model_name(chat_request, credentials, "gpt-4o-mini")
    url = f"{endpoint}/v1/chat/completions"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": _build_chat_messages(chat_request),
        "temperature": chat_request.temperature,
        "max_tokens": chat_request.max_tokens,
    }

    response_json = _post_json(url, payload, headers={"Authorization": f"Bearer {api_key}"})
    choices = response_json.get("choices", []) if isinstance(response_json, dict) else []
    reply = ""
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            msg = first_choice.get("message", {})
            if isinstance(msg, dict):
                reply = str(msg.get("content", ""))

    if not reply:
        reply = str(response_json)[:2000]

    return {
        "provider_id": provider.id,
        "provider": provider.provider,
        "endpoint": endpoint,
        "model": model,
        "reply": reply,
    }


def _chat_with_provider(provider: LlmProvider, chat_request: LlmProviderChatRequest) -> Dict[str, Any]:
    credentials = _decrypt_provider_credentials(provider)
    provider_type = provider.provider
    log_event(
        LOGGER,
        20,
        "llm.chat.dispatch",
        "Dispatching chat request to provider handler",
        provider_id=provider.id,
        provider=provider.provider,
        request_id=chat_request.request_id,
        conversation_id=chat_request.conversation_id,
        session_id=chat_request.session_id,
    )

    if provider_type in {"local_ollama", "ollama_cloud"}:
        return _chat_with_ollama(provider, credentials, chat_request)
    if provider_type in {"anthropic", "claude"}:
        return _chat_with_anthropic(provider, credentials, chat_request)
    if provider_type in {"ibm_watson", "aws_bedrock"}:
        return _chat_openai_compatible(provider, credentials, chat_request)

    log_event(
        LOGGER,
        40,
        "llm.chat.unsupported_provider",
        "Unsupported provider type",
        provider_id=provider.id,
        provider=provider.provider,
    )
    raise HTTPException(status_code=400, detail=f"Unsupported provider type: {provider_type}")

def get_provided_models(db: Session, provider_id: int) -> LLM_ModelsListResponse:
    log_event(LOGGER, 20, "llm.models.fetch.start", "Fetching provider models", provider_id=provider_id)
    provider = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
    if not provider:
        log_event(LOGGER, 30, "llm.models.fetch.not_found", "Provider not found while fetching models", provider_id=provider_id)
        raise HTTPException(status_code=404, detail="Provider not found")

    base = provider.endpoint.rstrip("/") if provider.endpoint else ""
    # Strip any trailing /v1 so we always build from the root base URL
    if base.endswith("/v1"):
        base = base[:-3]
    provider_endpoint = f"{base}/v1/models" if base else ""
    provider_credentials = _decrypt_provider_credentials(provider)

    if not provider_endpoint:
        log_event(LOGGER, 40, "llm.models.fetch.invalid_config", "Provider endpoint is not configured", provider_id=provider_id, provider=provider.provider)
        raise HTTPException(status_code=400, detail="Provider endpoint is not configured")
    if not provider_credentials.get("api_key"):
        log_event(LOGGER, 40, "llm.models.fetch.invalid_config", "Provider api_key credential is missing", provider_id=provider_id, provider=provider.provider)
        raise HTTPException(status_code=400, detail="Provider api_key credential is not configured")

    provider_type = provider.provider
    request_headers: Dict[str, str] = {"x-api-key": provider_credentials.get("api_key", "")}
    if provider_type in {"anthropic", "claude"}:
        request_headers["anthropic-version"] = "2023-06-01"

    log_event(
        LOGGER,
        20,
        "llm.models.fetch.upstream_call",
        "Calling provider models endpoint",
        provider_id=provider_id,
        provider=provider.provider,
        provider_type=provider_type,
        model_endpoint=provider_endpoint,
    )
    try:
        response_json = _get_json(provider_endpoint, headers=request_headers)
    except HTTPException as exc:
        log_event(
            LOGGER,
            40,
            "llm.models.fetch.failed",
            "Provider models fetch failed",
            provider_id=provider_id,
            provider=provider.provider,
            status_code=exc.status_code,
            detail=str(exc.detail),
        )
        raise

    llm_models = []
    for model in response_json.get("data", []):
        if isinstance(model, dict) and model.get("id"):
            model_obj = LLM_Model(
                provider_id=provider_id,
                provider=provider.provider,
                model_endpoint=provider_endpoint,
                id=str(model.get("id")),
                display_name=model.get("display_name") or model.get("name") or model.get("id"),
                created_at=model.get("created_at"),
                type=model.get("type"),
                capabilities=model.get("capabilities"),
                max_input_tokens=model.get("max_input_tokens"),
                max_tokens=model.get("max_tokens"),
            )
            llm_models.append(model_obj)

    log_event(
        LOGGER,
        20,
        "llm.models.fetch.completed",
        "Fetched provider models successfully",
        provider_id=provider_id,
        provider=provider.provider,
        model_count=len(llm_models),
    )
    return LLM_ModelsListResponse(models=llm_models)
