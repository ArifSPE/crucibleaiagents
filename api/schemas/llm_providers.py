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

