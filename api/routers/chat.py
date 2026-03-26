import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from schemas.model import ChatMessage, AgentPackage
from utils import dependency as dependencies
from utils.logger import get_logger, log_event, log_exception
from schemas.llm_providers import LLMProviderChatRequest,LLM_PROVIDER_CREDENTIAL_TEMPLATES, ALLOWED_LLM_PROVIDERS
from schemas.model import LlmProvider

router = APIRouter(prefix="/", tags=["chat"] )
_LOGGER = get_logger("api.routers.chat")


@router.post("/chat/{llm_provider_id}")
def chat_with_provider(llm_provider_id: int, body: LLMProviderChatRequest):
    with dependencies.db_session() as db:
        provider = db.query(LlmProvider).filter(LlmProvider.id == llm_provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="LLM provider not found")
 
        # Here you would implement the actual call to the LLM provider's API using the creds and message
        # For demonstration, we'll just return a mock response
        response_message = f"Echo from {provider.provider}: {body.message}"

        log_event(_LOGGER,  "chat.message", f"Sent message to {provider.provider}", provider_id=provider.id)

        return JSONResponse(content={"response": response_message})