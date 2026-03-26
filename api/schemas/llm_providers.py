from typing import Optional, Dict
from pydantic import BaseModel

class LLMProviderUpsert(BaseModel):
    provider_name: str
    description: Optional[str] = None
    endpoint: Optional[str] = None
    credentials: Optional[Dict[str, str]] = None  # Dict of credential key-values

class LLMProviderChatRequest(BaseModel):
    provider_name: str
    model: Optional[str] = None  # Optional model name or ID to use with the provider
    system_prompt: Optional[str] = None  # Optional system prompt to guide the conversation
    messages: list[Dict[str, str]]  # List of {"role": "user/assistant/system", "content": "message text"}
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

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
