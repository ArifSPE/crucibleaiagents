import json
from urllib import request as urllib_request
from urllib import error as urllib_error
from typing import Dict, Any, Optional, List
from fastapi import HTTPException
from schemas.model import LlmProvider
from utils.secrets_manager import get_secrets_manager
from utils.config import ALLOWED_LLM_PROVIDERS
from schemas.llm_providers import LLMProviderChatRequest as LlmProviderChatRequest


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


def _serialize_llm_provider(db_provider: LlmProvider) -> Dict[str, Any]:
    from services.run_service import _to_utc_iso
    credential_keys: List[str] = []
    has_credentials = bool(db_provider.encrypted_credentials and str(db_provider.encrypted_credentials).strip())

    if has_credentials:
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
    }


def _decrypt_provider_credentials(db_provider: LlmProvider) -> Dict[str, str]:
    if not db_provider.encrypted_credentials or not str(db_provider.encrypted_credentials).strip():
        return {}

    try:
        decrypted = get_secrets_manager().decrypt(db_provider.encrypted_credentials)
        parsed = json.loads(decrypted) if decrypted else {}
        if isinstance(parsed, dict):
            return {str(k): "" if v is None else str(v) for k, v in parsed.items()}
    except Exception:
        return {}
    return {}


def _post_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None, timeout_seconds: int = 30) -> Dict[str, Any]:
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
            return json.loads(body) if body else {}
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
        detail = body.strip() or f"Provider HTTP error: {exc.code}"
        raise HTTPException(status_code=502, detail=f"Provider request failed ({exc.code}): {detail[:400]}")
    except urllib_error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Provider connection failed: {exc.reason}")
    except Exception as exc:
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
    messages: List[Dict[str, str]] = []
    system_prompt = (chat_request.system_prompt or "").strip()
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": chat_request.message})
    return messages


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

    url = f"{endpoint}/v1/messages"
    payload: Dict[str, Any] = {
        "model": model,
        "max_tokens": chat_request.max_tokens or 256,
        "messages": [{"role": "user", "content": chat_request.message}],
    }
    system_prompt = (chat_request.system_prompt or "").strip()
    if system_prompt:
        payload["system"] = system_prompt
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

    if provider_type in {"local_ollama", "ollama_cloud"}:
        return _chat_with_ollama(provider, credentials, chat_request)
    if provider_type in {"anthropic", "claude"}:
        return _chat_with_anthropic(provider, credentials, chat_request)
    if provider_type in {"ibm_watson", "aws_bedrock"}:
        return _chat_openai_compatible(provider, credentials, chat_request)

    raise HTTPException(status_code=400, detail=f"Unsupported provider type: {provider_type}")
