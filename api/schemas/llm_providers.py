from __future__ import annotations

from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class LLMProviderUpsert(BaseModel):
    provider_name: str
    description: Optional[str] = None
    endpoint: Optional[str] = None
    credentials: Optional[Dict[str, str]] = None  # Dict of credential key-values
    created_datetime: Optional[str] = None  # ISO format datetime string, e.g., "2024-01-01T12:00:00Z"
    updated_datetime: Optional[str] = None  # ISO format datetime string, e.g.,


class LLMChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("Message content cannot be empty")
        return content


class LLMProviderChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_name: str
    # Backward compatibility for older clients that send a single user prompt.
    message: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    model: Optional[str] = None  # Optional model name or ID to use with the provider
    system_prompt: Optional[str] = None  # Optional system prompt to guide the conversation
    messages: list[LLMChatMessage] = Field(default_factory=list)
    # Optional short-term memory context injected before current-turn messages.
    short_term_memory: list[LLMChatMessage] = Field(default_factory=list)
    memory_strategy: Literal["append", "window", "summary"] = "window"
    memory_window_size: int = Field(default=20, ge=1, le=200)
    conversation_id: Optional[str] = Field(default=None, max_length=128)
    session_id: Optional[str] = Field(default=None, max_length=128)
    request_id: Optional[str] = Field(default=None, max_length=128)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=32768)
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("provider_name", "model", "system_prompt", "message", "conversation_id", "session_id", "request_id")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def validate_message_inputs(self) -> "LLMProviderChatRequest":
        has_legacy_message = bool(self.message)
        has_messages = bool(self.messages)
        if not has_legacy_message and not has_messages:
            raise ValueError("Either `messages` or legacy `message` must be provided")

        if len(self.messages) + len(self.short_term_memory) > 400:
            raise ValueError("Combined message history is too large; keep total messages <= 400")

        return self

    def build_messages(self) -> list[Dict[str, str]]:
        """Build normalized provider-ready chat messages.

        Order:
        1) explicit system_prompt (if provided)
        2) short_term_memory
        3) request messages
        4) legacy single message (as final user turn, for backward compatibility)
        """
        combined: list[Dict[str, str]] = []

        if self.system_prompt:
            combined.append({"role": "system", "content": self.system_prompt})

        for msg in self.short_term_memory:
            combined.append({"role": msg.role, "content": msg.content})

        for msg in self.messages:
            combined.append({"role": msg.role, "content": msg.content})

        if self.message:
            if not combined or not (
                combined[-1].get("role") == "user" and combined[-1].get("content") == self.message
            ):
                combined.append({"role": "user", "content": self.message})

        if self.memory_strategy == "window":
            # Keep the latest N non-system turns, but preserve the first system prompt if present.
            system_prefix = combined[0] if combined and combined[0].get("role") == "system" else None
            non_system = [msg for msg in combined if msg.get("role") != "system"]
            trimmed = non_system[-self.memory_window_size:]
            if system_prefix:
                return [system_prefix, *trimmed]
            return trimmed

        return combined

    def latest_user_message(self) -> str:
        for msg in reversed(self.build_messages()):
            if msg.get("role") == "user":
                return str(msg.get("content", ""))
        return ""

ALLOWED_LLM_PROVIDERS = {
    "local_ollama",
    "ollama_cloud",
    "ibm_watson",
    "aws_bedrock",
    "anthropic",
    "claude",
}

# Provider-specific credential templates
LLM_PROVIDER_CREDENTIAL_TEMPLATES = {
    "local_ollama": [],  # No credentials needed
    "ollama_cloud": ["api_key"],
    "ibm_watson": ["api_key", "instance_id"],
    "aws_bedrock": ["access_key_id", "secret_access_key", "region"],
    "anthropic": ["api_key"],
    "claude": ["api_key"],
}
