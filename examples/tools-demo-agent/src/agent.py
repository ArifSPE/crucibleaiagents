"""
Platform Tools Demo Agent

Demonstrates the full capabilities of AgentFlow platform tools:
- LLM reasoning and tool selection
- Safe shell command execution
- HTTP requests (curl-like operations)
- Custom tool registration and execution

This agent showcases agentic behavior: given a task, it reasons about
which tools to use and executes them to complete the task.
"""

import os
import json
from platform_sdk import (
    get_logger,
    step,
    LLMClient,
    ShellExecutor,
    HTTPClient,
    ToolRegistry,
    ToolParameter,
)

# Initialize logger
logger = get_logger("agent")


@step("initialize_tools")
def initialize_tools():
    """Initialize all platform tools with safe configurations."""
    logger.info("Initializing platform tools...")
    
    # LLM client for reasoning
    llm = LLMClient(
        model=os.getenv("LLM_MODEL", "llama3.1"),
        temperature=0.7
    )
    
    # Shell executor with allowlist of safe commands
    shell = ShellExecutor(
        allowed_commands=[
            "ls", "cat", "grep", "echo", "pwd", "date", 
            "wc", "head", "tail", "find", "which", "git"
        ],
        timeout=30
    )
    
    # HTTP client for web requests
    http = HTTPClient(timeout=30)
    
    # Custom tool registry
    registry = ToolRegistry()
    
    logger.info("Tools initialized successfully")
    return llm, shell, http, registry


@step("register_custom_tools")
def register_custom_tools(registry):
    """Register custom domain-specific tools."""
    
    @registry.tool(
        name="analyze_json",
        description="Parse and analyze JSON data, extract specific fields",
        parameters=[
            ToolParameter("json_string", "string", "JSON string to analyze"),
            ToolParameter("field_path", "string", "Dot-notation path to extract (e.g., 'data.items[0].name')", required=False),
        ]
    )
    def analyze_json(json_string: str, field_path: str = None):
        """Analyze JSON data."""
        try:
            data = json.loads(json_string)
            
            if field_path:
                # Simple path extraction (doesn't support full JSONPath)
                parts = field_path.split('.')
                current = data
                for part in parts:
                    current = current[part]
                return current
            
            return {
                "parsed": True,
                "keys": list(data.keys()) if isinstance(data, dict) else None,
                "length": len(data) if isinstance(data, (dict, list)) else None,
                "type": type(data).__name__
            }
        except Exception as e:
            return {"error": str(e)}
    
    @registry.tool(
        name="calculate",
        description="Perform mathematical calculations",
        parameters=[
            ToolParameter("expression", "string", "Math expression to evaluate (e.g., '2 + 2', '5 * 10 / 2')"),
        ]
    )
    def calculate(expression: str):
        """Safe calculator (uses eval with restricted namespace)."""
        try:
            # Restricted namespace - only allow basic math operations
            allowed_names = {
                'abs': abs, 'round': round, 'min': min, 'max': max,
                'sum': sum, 'pow': pow
            }
            result = eval(expression, {"__builtins__": {}}, allowed_names)
            return {"result": result, "expression": expression}
        except Exception as e:
            return {"error": str(e), "expression": expression}
    
    logger.info(f"Registered {len(registry.list_tools())} custom tools")
    return registry


@step("demonstrate_llm_reasoning")
def demonstrate_llm_reasoning(llm):
    """Show LLM reasoning capabilities."""
    logger.info("=== LLM Reasoning Demo ===")
    
    # Simple reasoning task
    response = llm.chat(
        message="What are the top 3 use cases for AI agents in software development?",
        system="You are a helpful AI assistant. Be concise and use bullet points."
    )
    
    logger.info(f"LLM Response ({response.latency_ms:.0f}ms):")
    logger.info(response.content)
    
    return response


@step("demonstrate_shell_commands")
def demonstrate_shell_commands(shell):
    """Show safe shell command execution."""
    logger.info("=== Shell Commands Demo ===")
    
    # List current directory
    result = shell.run("ls -la")
    logger.info(f"Directory listing (exit code: {result.exit_code}):")
    logger.info(result.stdout[:500])  # First 500 chars
    
    # Get current working directory
    result = shell.run("pwd")
    logger.info(f"Working directory: {result.stdout.strip()}")
    
    # Try to run a disallowed command (will fail gracefully)
    try:
        result = shell.run("rm -rf /")  # Blocked!
        logger.warning("Dangerous command was executed! Security issue!")
    except ValueError as e:
        logger.info(f"✓ Security check passed: {e}")
    
    return result


@step("demonstrate_http_requests")
def demonstrate_http_requests(http):
    """Show HTTP client capabilities."""
    logger.info("=== HTTP Requests Demo ===")
    
    # GET request to a public API
    response = http.get("https://api.github.com/repos/python/cpython")
    logger.info(f"GET request completed: {response.status_code} ({response.duration_ms:.0f}ms)")
    
    # Parse response
    data = json.loads(response.body)
    logger.info(f"Repository: {data.get('full_name')}")
    logger.info(f"Stars: {data.get('stargazers_count')}")
    logger.info(f"Language: {data.get('language')}")
    
    return response


@step("demonstrate_custom_tools")
def demonstrate_custom_tools(registry):
    """Show custom tool execution."""
    logger.info("=== Custom Tools Demo ===")
    
    # List available tools
    tools = registry.list_tools()
    logger.info(f"Available custom tools: {[t['name'] for t in tools]}")
    
    # Use calculator tool
    result = registry.execute("calculate", {"expression": "2 + 2 * 10"})
    logger.info(f"Calculator: {result}")
    
    # Use JSON analyzer tool
    sample_json = json.dumps({
        "status": "success",
        "data": {
            "items": [
                {"id": 1, "name": "Item A"},
                {"id": 2, "name": "Item B"}
            ]
        }
    })
    
    result = registry.execute("analyze_json", {"json_string": sample_json})
    logger.info(f"JSON analysis: {result}")
    
    return result


@step("demonstrate_agentic_workflow")
def demonstrate_agentic_workflow(llm, shell, http, registry):
    """
    Demonstrate an agentic workflow where the LLM reasons about
    which tools to use for a given task.
    """
    logger.info("=== Agentic Workflow Demo ===")
    
    # Define a task
    task = """
    Task: Get information about the current system and analyze it.
    
    Available tools:
    1. shell - Run commands like 'pwd', 'date', 'ls'
    2. http - Make HTTP requests
    3. calculate - Perform calculations
    4. analyze_json - Parse JSON data
    
    Plan and execute the steps needed to complete this task.
    """
    
    # Get LLM to create a plan
    response = llm.chat(
        message=task,
        system="You are an AI agent. Create a step-by-step plan to complete the task. Be specific about which commands to run."
    )
    
    logger.info("LLM Plan:")
    logger.info(response.content)
    
    # Execute the plan (simplified - in real agent this would be ReAct loop)
    logger.info("\nExecuting plan...")
    
    # Step 1: Get system info
    result = shell.run("date")
    system_date = result.stdout.strip()
    logger.info(f"1. System date: {system_date}")
    
    # Step 2: Get working directory
    result = shell.run("pwd")
    work_dir = result.stdout.strip()
    logger.info(f"2. Working directory: {work_dir}")
    
    # Step 3: List files
    result = shell.run("ls -1")
    files = result.stdout.strip().split('\n')
    file_count = len(files)
    logger.info(f"3. File count: {file_count} files")
    
    # Step 4: Calculate summary
    calc_result = registry.execute("calculate", {"expression": f"{file_count} * 2"})
    logger.info(f"4. Calculation result: {calc_result}")
    
    # Step 5: Create summary JSON
    summary = {
        "timestamp": system_date,
        "working_directory": work_dir,
        "file_count": file_count,
        "calculation": calc_result
    }
    
    analysis = registry.execute("analyze_json", {
        "json_string": json.dumps(summary)
    })
    logger.info(f"5. Summary analysis: {analysis}")
    
    # Final LLM summary
    final_prompt = f"""
    Based on the following information, provide a brief summary:
    
    {json.dumps(summary, indent=2)}
    
    Summarize what was discovered in 2-3 sentences.
    """
    
    response = llm.chat(message=final_prompt)
    logger.info("\nFinal Summary:")
    logger.info(response.content)
    
    return summary


def main():
    """Main agent execution."""
    logger.info("========================================")
    logger.info("Platform Tools Demo Agent Started")
    logger.info("========================================")
    
    try:
        # Initialize tools
        llm, shell, http, registry = initialize_tools()
        
        # Register custom tools
        registry = register_custom_tools(registry)
        
        # Run demonstrations
        demonstrate_llm_reasoning(llm)
        demonstrate_shell_commands(shell)
        demonstrate_http_requests(http)
        demonstrate_custom_tools(registry)
        
        # Show agentic workflow
        demonstrate_agentic_workflow(llm, shell, http, registry)
        
        logger.info("========================================")
        logger.info("Demo completed successfully!")
        logger.info("========================================")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
