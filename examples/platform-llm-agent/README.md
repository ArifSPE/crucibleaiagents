# Platform LLM Provider Agent Example

This example demonstrates how to use the AgentFlow platform LLM provider feature, which allows you to centrally manage LLM credentials and automatically inject them into your agents.

**This example is configured to use Provider #4 (Local Ollama).**

## Overview

Instead of managing API keys in each agent's secrets, you can:

1. Configure LLM providers at the platform level (OpenAI, Anthropic, AWS Bedrock, etc.)
2. Reference the provider in your manifest using `llm_provider.provider_id`
3. The platform automatically injects the appropriate credentials at runtime

## Benefits

- **Centralized Management**: Manage API keys in one place
- **Easy Rotation**: Update credentials without modifying agents
- **Multi-Provider Support**: Switch between providers without code changes
- **Security**: Credentials never appear in manifests or logs

## Manifest Configuration

```json
{
  "name": "platform-llm-agent",
  "llm_provider": {
    "use_platform": true,
    "provider_id": 1
  }
}
```

## Setup

### 1. Verify Platform LLM Provider

This example is configured to use **Provider #4 (Local Ollama)**. Verify it exists:

```bash
curl http://localhost:8080/llm-providers/4
```

Expected response:
```json
{
  "id": 4,
  "provider": "local_ollama",
  "description": "My Local Ollama",
  "endpoint": "http://host.docker.internal:11434",
  "has_credentials": false,
  "credential_keys": []
}
```

If provider #4 doesn't exist or is different, either:
- Update `manifest.json` with the correct `provider_id`, or
- Create a new local Ollama provider:

```bash
curl -X POST http://localhost:8080/llm-providers \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "local_ollama",
    "description": "Local Ollama",
    "endpoint": "http://host.docker.internal:11434"
  }'
```

### 2. Ensure Ollama is Running

Make sure Ollama is running on your local machine with the llama3.1 model:

```bash
ollama list  # Check if llama3.1 is available
ollama pull llama3.1  # Download if needed ✓ **Used in this example**
```

### 3. Package and Upload
 and uses the appropriate LangChain integration:

```python
import os
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from platform_sdk import get_logger

log = get_logger("agent")

# Credentials/endpoint are automatically available
if os.environ.get("OPENAI_API_KEY"):
    llm = ChatOpenAI()
elif os.environ.get("ANTHROPIC_API_KEY"):
    llm = ChatAnthropic()
elif os.environ.get("LLM_ENDPOINT"):
    llm = ChatOllama(
        base_url=os.environ.get("LLM_ENDPOINT"),
        model=os.environ.get("MODEL_NAME", "llama3.1")
    
## Supported Providers

- **OpenAI**: Injects `OPENAI_API_KEY`
- **Anthropic/Claude**: Injects `ANTHROPIC_API_KEY`
- **Ollama Cloud**: Injects `OLLAMA_API_KEY`
- **AWS Bedrock**: Injects `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
- **IBM Watson**: Injects `WATSONX_API_KEY`, `WATSONX_INSTANCE_ID`
- **Local Ollama**: Injects `LLM_ENDPOINT` (no credentials needed)

## Agent Code

The agent automatically detects which provider is configured:

```python
import os
from langchain_openai import ChatOpenAI
from platform_sdk import get_logger

log = get_logger("agent")

# Credentials are automatically available
llm = ChatOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("LLM_ENDPOINT")  # If custom endpoint configured
)

response = llm.invoke("Hello!")
log.info(f"Response: {response.content}")
```

## Hybrid Configuration

You can combine platform providers with manifest environment variables:

```json
{
  "llm_provider": {
    "use_platform": true,
    "provider_id": 1
  },
  "environment": {
    "MODEL_NAME": "gpt-4",
    "FALLBACK_ENDPOINT": "http://localhost:11434"
  }
}
```

Priority (highest to lowest):
1. Package secrets (e.g., `{secrets.MY_KEY}`)
2. Manifest environment variables
3. Platform LLM provider credentials

## Troubleshooting

### No LLM credentials found

- Verify the provider ID in your manifest matches an existing provider
- Check the provider has credentials configured: `GET /llm-providers/{id}`
- Ensure the provider is the correct type for your agent's dependencies

### Wrong provider type

- Check your agent's `requirements.txt` matches the provider type
- OpenAI provider requires `langchain-openai`
- Anthropic provider requires `langchain-anthropic`
- Use a provider-agnostic approach or install multiple LangChain integrations

## See Also

- [LLM Provider Documentation](../../docs/LLM_PROVIDER.md)
- [Secrets Management](../../SECRETS_GUIDE.md)
- [Manifest Schema](../../docs/SCHEDULE_LOADING.md)
