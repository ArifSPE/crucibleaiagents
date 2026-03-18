"""
Platform LLM Provider Agent Example

This agent demonstrates how to use the platform LLM provider feature,
which automatically injects LLM credentials from a centrally managed provider.

The agent automatically detects which LLM provider is configured and uses it.
"""

import os
import sys
from platform_sdk import get_logger

log = get_logger("agent")

def main():
    log.info("Starting platform LLM agent")
    
    # Check which LLM credentials are available
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    llm_endpoint = os.environ.get("LLM_ENDPOINT")
    
    log.info(f"Environment check:")
    log.info(f"  - OPENAI_API_KEY: {'✓ Set' if openai_key else '✗ Not set'}")
    log.info(f"  - ANTHROPIC_API_KEY: {'✓ Set' if anthropic_key else '✗ Not set'}")
    log.info(f"  - LLM_ENDPOINT: {llm_endpoint if llm_endpoint else '✗ Not set'}")
    
    # Use OpenAI if available
    if openai_key:
        log.info("Using OpenAI provider")
        use_openai()
    # Use Anthropic if available
    elif anthropic_key:
        log.info("Using Anthropic provider")
        use_anthropic()
    # Use Ollama if endpoint is available
    elif llm_endpoint:
        log.info("Using Ollama provider")
        use_ollama()
    else:
        log.error("No LLM credentials found. Please configure a platform LLM provider.")
        sys.exit(1)
    
    log.info("Agent completed successfully")

def use_openai():
    """Use OpenAI API with platform credentials."""
    try:
        from langchain_openai import ChatOpenAI
        
        model_name = os.environ.get("MODEL_NAME", "gpt-4")
        temperature = float(os.environ.get("DEFAULT_TEMPERATURE", "0.7"))
        endpoint = os.environ.get("LLM_ENDPOINT")
        
        log.info(f"Initializing OpenAI with model: {model_name}")
        
        llm_kwargs = {
            "model": model_name,
            "temperature": temperature,
        }
        
        if endpoint:
            llm_kwargs["base_url"] = endpoint
            log.info(f"Using custom endpoint: {endpoint}")
        
        llm = ChatOpenAI(**llm_kwargs)
        
        # Test the LLM
        log.info("Testing LLM connection...")
        response = llm.invoke("Say 'Hello from AgentFlow!' and nothing else.")
        log.info(f"LLM Response: {response.content}")
        
    except Exception as e:
        log.error(f"Failed to use OpenAI: {e}")
        raise

def use_anthropic():
    """Use Anthropic API with platform credentials."""
    try:
        from langchain_anthropic import ChatAnthropic
        
        model_name = os.environ.get("MODEL_NAME", "claude-3-sonnet-20240229")
        temperature = float(os.environ.get("DEFAULT_TEMPERATURE", "0.7"))
        
        log.info(f"Initializing Anthropic with model: {model_name}")
        
        llm = ChatAnthropic(
            model=model_name,
            temperature=temperature,
        )
        
        # Test the LLM
        log.info("Testing LLM connection...")
        response = llm.invoke("Say 'Hello from AgentFlow!' and nothing else.")
        log.info(f"LLM Response: {response.content}")
        
    except Exception as e:
        log.error(f"Failed to use Anthropic: {e}")
        raise

def use_ollama():
    """Use Ollama API with platform endpoint."""
    try:
        from langchain_ollama import ChatOllama
        
        endpoint = os.environ.get("LLM_ENDPOINT")
        model_name = os.environ.get("MODEL_NAME", "llama3.1")
        temperature = float(os.environ.get("DEFAULT_TEMPERATURE", "0.7"))
        
        log.info(f"Initializing Ollama with model: {model_name}")
        log.info(f"Using endpoint: {endpoint}")
        
        llm = ChatOllama(
            base_url=endpoint,
            model=model_name,
            temperature=temperature,
        )
        
        # Test the LLM
        log.info("Testing LLM connection...")
        response = llm.invoke("Say 'Hello from AgentFlow!' and nothing else.")
        log.info(f"LLM Response: {response.content}")
        
    except Exception as e:
        log.error(f"Failed to use Ollama: {e}")
        raise

if __name__ == "__main__":
    main()
