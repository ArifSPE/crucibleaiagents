import os
import json
import logging
from typing import List, Dict, Sequence, Annotated, TypedDict
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage, SystemMessage
from langchain_tavily import TavilySearch
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph.message import add_messages

# Try to import platform SDK for instrumentation and logging
try:
    from platform_sdk import step, get_logger
    log = get_logger("agent")  # Use platform logger that saves to database
except ImportError:
    # Fallback if not running in platform
    log = logging.getLogger(__name__)
    
    def step(name):
        def decorator(func):
            return func
        return decorator

# Environment configuration
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

# Set Tavily API key only when configured
if TAVILY_API_KEY:
    os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY


@tool
def sanity_tool(query: str) -> str:
    """Return a fixed response for testing."""
    return "ok"


@tool
def search_tool(query: str) -> str:
    """
    Search the web for information using Tavily API.

    :param query: The search query string
    :return: Search results related to the query
    """
    if not TAVILY_API_KEY:
        return "Search tool is disabled because TAVILY_API_KEY is not configured."

    search = TavilySearch()
    result = search.invoke({"query": query})

    # Convert structured output to string
    if isinstance(result, dict):
        return result.get("answer") or str(result)

    return str(result)


@tool
def recommend_clothing(temperature: float) -> str:
    """
    Recommend clothing based on the given temperature.

    :param temperature: The current temperature in degrees Celsius
    :return: A clothing recommendation string
    """
    if temperature < 0:
        return "It's freezing! Wear a heavy coat, gloves, and a hat."
    elif 0 <= temperature < 10:
        return "It's cold. Wear a coat and maybe a scarf."
    elif 10 <= temperature < 20:
        return "It's cool. A light jacket or sweater should be fine."
    elif 20 <= temperature < 30:
        return "It's warm. A t-shirt and shorts would be comfortable."
    else:
        return "It's hot! Wear light clothing and stay hydrated."


class AgentState(TypedDict):
    """State definition for the agent."""
    messages: Annotated[Sequence[BaseMessage], add_messages]


@step("initialize_agent")
def initialize_agent():
    """Initialize the LLM and tools."""
    log.info(f"Initializing agent with Ollama model: {OLLAMA_MODEL}")
    
    tools = [sanity_tool, recommend_clothing]
    if TAVILY_API_KEY:
        tools.append(search_tool)
    else:
        log.warning("TAVILY_API_KEY not set; Tavily search tool disabled")
    tools_by_name = {tool.name: tool for tool in tools}
    
    llm = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
    ).bind_tools(tools)
    
    log.info("✅ Agent initialized with tools: %s", [t.name for t in tools])
    return llm, tools_by_name


@step("process_query")
def process_query(llm, tools_by_name, user_query: str, max_iterations: int = 5):
    """
    Process a user query using the ReAct pattern.
    
    :param llm: The language model with bound tools
    :param tools_by_name: Dictionary of available tools
    :param user_query: The user's question
    :param max_iterations: Maximum number of reasoning iterations
    :return: Final response
    """
    log.info(f"Processing query: {user_query}")
    
    # Initialize state with system message and user query
    state: AgentState = {
        "messages": [
            SystemMessage(content="You are a helpful assistant. Use the available tools to answer questions."),
            HumanMessage(content=user_query)
        ]
    }
    
    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        log.info(f"Iteration {iteration}/{max_iterations}")
        
        # Get LLM response
        response = llm.invoke(state["messages"])
        state["messages"] = add_messages(state["messages"], [response])
        
        # Check if LLM wants to use tools
        if not response.tool_calls:
            log.info("No tool calls. Agent has finished reasoning.")
            return response.content
        
        # Execute tool calls
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            log.info(f"Calling tool: {tool_name} with args: {tool_args}")
            
            try:
                # Execute the tool
                tool_result = tools_by_name[tool_name].invoke(tool_args)
                log.info(f"Tool result preview: {str(tool_result)[:200]}")
                
                # Add tool result to state
                tool_message = ToolMessage(
                    content=str(tool_result),
                    name=tool_name,
                    tool_call_id=tool_call["id"]
                )
                state["messages"] = add_messages(state["messages"], [tool_message])
                
            except Exception as e:
                log.error(f"Error executing tool {tool_name}: {e}")
                error_message = ToolMessage(
                    content=f"Error: {str(e)}",
                    name=tool_name,
                    tool_call_id=tool_call["id"]
                )
                state["messages"] = add_messages(state["messages"], [error_message])
    
    log.warning("Reached max iterations without final answer")
    return "I've reached the maximum number of reasoning steps. Here's what I found so far."


@step("run_agent")
def run_agent():
    """Main agent execution."""
    log.info("Starting ReAct Ollama Agent")
    
    # Initialize agent
    llm, tools_by_name = initialize_agent()
    
    # Example queries
    queries = [
        "What's the weather in Zurich? and What should I wear today based on temperature?",
        "Search for the latest news about AI",
        "If it's 15 degrees Celsius, what should I wear?"
    ]
    
    # Process first query (or all queries based on your needs)
    query = queries[0]
    log.info(f"\n{'='*60}")
    log.info(f"Query: {query}")
    log.info(f"{'='*60}")
    
    result = process_query(llm, tools_by_name, query)
    
    log.info(f"\n{'='*60}")
    log.info(f"Final Answer: {result}")
    log.info(f"{'='*60}")
    
    return result


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the agent
    run_agent()
    
    log.info("Agent execution completed")
