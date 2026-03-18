#!/usr/bin/env python3
"""
MS Teams Channel Summarizer Agent

This agent:
1. Reads messages from a configured MS Teams channel
2. Summarizes the messages using an LLM
3. Posts the summary back to the channel
4. Supports scheduled runs and webhook triggers
"""

import os
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
import structlog

# Import the MS Teams integration
try:
    # Try relative import first (for package usage)
    from .msteams_integration import MSTeamClient, MSTeamsConfig, read_channel_messages_tool, post_channel_message_tool
except ImportError:
    # Fall back to direct import (for direct execution)
    from msteams_integration import MSTeamClient, MSTeamsConfig, read_channel_messages_tool, post_channel_message_tool

# Simple LLM integration (can be replaced with OpenAI, Ollama, etc.)
try:
    import httpx
    HAS_HTTP = True
except ImportError:
    HAS_HTTP = False
    httpx = None

# WebSocket support
try:
    import websockets
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False
    websockets = None

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

class MessageSummarizer:
    """Simple message summarizer that can use various LLM backends."""
    
    def __init__(
        self,
        llm_endpoint: Optional[str] = None,
        llm_model: str = "llama3.1",
        system_prompt: Optional[str] = None,
    ):
        self.llm_endpoint = llm_endpoint
        self.llm_model = llm_model
        self.system_prompt = (system_prompt or "").strip()
        self.use_simple_summarizer = not (llm_endpoint and HAS_HTTP)
        
        if self.use_simple_summarizer:
            logger.warning("Using simple rule-based summarizer. Set LLM_ENDPOINT for better summaries.")
        else:
            logger.info("Using LLM for message summarization", endpoint=llm_endpoint, model=llm_model)
    
    async def summarize_messages(self, messages: List[Dict[str, Any]]) -> str:
        """Summarize a list of messages."""
        if not messages:
            return "No messages to summarize."
        
        if self.use_simple_summarizer:
            return self._simple_summarize(messages)
        else:
            return await self._llm_summarize(messages)
    
    def _simple_summarize(self, messages: List[Dict[str, Any]]) -> str:
        """Simple rule-based message summarization."""
        if len(messages) == 0:
            return "No new messages in the channel."
        
        # Group messages by user
        user_messages = {}
        total_messages = len(messages)
        
        for msg in messages:
            user = msg.get("from", "Unknown")
            if user not in user_messages:
                user_messages[user] = []
            user_messages[user].append(msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"])
        
        # Sort users by message count (descending)
        sorted_users = sorted(user_messages.items(), key=lambda x: len(x[1]), reverse=True)
        
        # Create summary
        summary_parts = [
            f"📊 Channel Activity Summary ({total_messages} messages)",
            "",
            f"Active participants: {', '.join([user for user, _ in sorted_users])}",
            "",
            "Key discussions:"
        ]
        
        # Add discussions by user (sorted by message count)
        for user, user_msgs in sorted_users[:5]:  # Top 5 users
            if len(user_msgs) > 0:
                summary_parts.append(f"• {user} ({len(user_msgs)} messages):{user_msgs[0]}")
        
        # Add timestamp
        summary_parts.extend([
            "",
            f"_Summary generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
        ])
        
        return "\n".join(summary_parts)
    
    async def _llm_summarize(self, messages: List[Dict[str, Any]]) -> str:
        """Use LLM to create a more sophisticated summary."""
        # Prepare messages for LLM
        message_text = ""
        for msg in messages:
            timestamp = msg.get("created_datetime", "")
            user = msg.get("from", "Unknown")
            content = msg.get("content", "")
            message_text += f"[{timestamp}] {user}: {content}\\n"
        
        base_prompt = """Please provide a concise summary of the following MS Teams channel messages.
    Focus on key discussions, decisions, action items, and participant engagement.

Messages:
{message_text}

Provide a structured summary in the following format:
- **Main Topics**: List of key discussion topics
- **Participants**: Who was actively engaged  
- **Key Points**: Important information or decisions
- **Action Items**: Any tasks or follow-ups mentioned
- **Activity Level**: Brief assessment of channel activity

Keep the summary professional and under 500 characters."""

        # Apply manifest-provided system prompt when available.
        if self.system_prompt:
            prompt = (
                f"System instructions:\n{self.system_prompt}\n\n"
                f"User task:\n{base_prompt}"
            )
        else:
            prompt = base_prompt
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.llm_endpoint}/api/generate",
                    json={
                        "model": self.llm_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "top_p": 0.9,
                            "max_tokens": 500
                        }
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    summary = result.get("response", "Failed to generate summary")
                    logger.info("LLM summary generated successfully")
                    return summary
                else:
                    logger.error("LLM request failed", status_code=response.status_code)
                    return self._simple_summarize(messages)
                    
        except Exception as e:
            logger.error("Error calling LLM", error=str(e))
            return self._simple_summarize(messages)

def load_manifest() -> Dict[str, Any]:
    """Load configuration from manifest.json file."""
    try:
        # Try to find manifest.json in current directory or parent directory
        manifest_paths = [
            Path.cwd() / "manifest.json",
            Path.cwd().parent / "manifest.json",
            Path(__file__).parent.parent / "manifest.json"
        ]
        
        for manifest_path in manifest_paths:
            if manifest_path.exists():
                with open(manifest_path, 'r') as f:
                    return json.load(f)
        
        logger.warning("No manifest.json found, using environment variables only")
        return {}
        
    except Exception as e:
        logger.error("Error loading manifest.json", error=str(e))
        return {}

class WebSocketClient:
    """WebSocket client for real-time Teams integration."""
    
    def __init__(self, websocket_url: str, summarizer_instance):
        if not HAS_WEBSOCKET:
            raise ImportError("websockets library is required for WebSocket functionality")
        
        self.websocket_url = websocket_url
        self.summarizer = summarizer_instance
        self.reconnect_interval = 30
        self.ping_interval = 60
        self.running = False
        
        logger.info("WebSocket client initialized", url=websocket_url)
    
    async def connect_and_listen(self):
        """Connect to WebSocket and listen for messages."""
        logger.info("Starting WebSocket connection")
        self.running = True
        
        while self.running:
            try:
                async with websockets.connect(self.websocket_url) as websocket:
                    logger.info("WebSocket connected successfully")
                    
                    # Send initial hello message
                    await websocket.send(json.dumps({
                        "type": "hello",
                        "agent": "msteam-channel-summarizer",
                        "timestamp": datetime.now().isoformat()
                    }))
                    
                    # Listen for messages
                    async for message in websocket:
                        try:
                            await self._handle_message(websocket, message)
                        except Exception as e:
                            logger.error("Error handling WebSocket message", error=str(e))
                            
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed, reconnecting...")
                await asyncio.sleep(self.reconnect_interval)
            except Exception as e:
                logger.error("WebSocket connection error", error=str(e))
                await asyncio.sleep(self.reconnect_interval)
    
    async def _handle_message(self, websocket, message: str):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")
            
            logger.info("Received WebSocket message", type=msg_type)
            
            if msg_type == "summarize_request":
                # Trigger immediate summarization
                result = await self.summarizer.run_summarization()
                
                # Send response back
                response = {
                    "type": "summarize_response",
                    "request_id": data.get("request_id"),
                    "success": result.get("success", False),
                    "timestamp": datetime.now().isoformat(),
                    "data": result
                }
                
                await websocket.send(json.dumps(response))
                logger.info("Sent summarization response", success=result.get("success"))
                
            elif msg_type == "channel_message":
                # Handle real-time channel message notification
                # This could be used to trigger summarization based on message volume
                self._handle_channel_message(data)
                
            elif msg_type == "status_request":
                # Send status information
                status = {
                    "type": "status_response", 
                    "request_id": data.get("request_id"),
                    "agent": "msteam-channel-summarizer",
                    "status": "running",
                    "timestamp": datetime.now().isoformat(),
                    "last_run": getattr(self.summarizer, 'last_run_time', None)
                }
                
                await websocket.send(json.dumps(status))
                
            elif msg_type == "ping":
                # Respond to ping
                pong = {
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(pong))
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON in WebSocket message")
        except Exception as e:
            logger.error("Error processing WebSocket message", error=str(e))
    
    def _handle_channel_message(self, data: Dict[str, Any]):
        """Handle real-time channel message notifications."""
        # This could implement logic like:
        # - Count messages in a time window
        # - Trigger summarization when threshold is reached
        # - Filter by message importance
        
        channel_id = data.get("channel_id")
        message_count = data.get("message_count", 0)
        
        logger.info("Channel message notification", 
                   channel_id=channel_id, 
                   message_count=message_count)
        
        # Example: trigger summarization if 10+ messages in short time
        if message_count >= 10:
            logger.info("Message threshold reached, scheduling summarization")
            # Could schedule an immediate summarization task here
    
    def stop(self):
        """Stop the WebSocket client."""
        logger.info("Stopping WebSocket client")
        self.running = False

class TeamsChannelSummarizer:
    """Main agent class that orchestrates the summarization workflow."""
    
    def __init__(self):
        # Load configuration from manifest and environment variables
        self.manifest = load_manifest()
        self.config = self._load_config()
        self.summarizer = MessageSummarizer(
            llm_endpoint=self.config.get("llm_endpoint"),
            llm_model=self.config.get("llm_model", "llama3.1"),
            system_prompt=self.config.get("system_prompt"),
        )
        self.last_run_time = None
        self.websocket_client = None
        
        # Initialize WebSocket client if enabled
        if self.config.get("websocket_enabled", "false").lower() == "true":
            websocket_url = self.config.get("websocket_url")
            if websocket_url and HAS_WEBSOCKET:
                self.websocket_client = WebSocketClient(websocket_url, self)
                logger.info("WebSocket client enabled", url=websocket_url)
            elif not HAS_WEBSOCKET:
                logger.warning("WebSocket requested but websockets library not installed")
            else:
                logger.warning("WebSocket enabled but no URL configured")
        
        logger.info("Teams Channel Summarizer initialized", 
                   team_id=self.config["team_id"],
                   channel_id=self.config["channel_id"],
                   destination_team_id=self.config.get("destination_team_id", "same as source"),
                   destination_channel_id=self.config.get("destination_channel_id", "same as source"),
                   webhook_url_configured=bool(self.config.get("webhook_url")),
                   websocket_enabled=self.websocket_client is not None)
    
    def _load_config(self) -> Dict[str, str]:
        """Load configuration from manifest and environment variables."""
        required_vars = [
            "MS_TEAMS_TENANT_ID",
            "MS_TEAMS_CLIENT_ID", 
            "MS_TEAMS_CLIENT_SECRET",
            "MS_TEAMS_TEAM_ID",
            "MS_TEAMS_CHANNEL_ID"
        ]
        
        config = {}
        missing_vars = []
        
        # Get manifest environment values
        manifest_env = self.manifest.get("environment", {})
        
        # Load from environment variables OR manifest
        for var in required_vars:
            # Try environment variable first, then manifest
            value = os.getenv(var) or manifest_env.get(var)
            if not value:
                missing_vars.append(var)
            else:
                config[var.lower().replace("ms_teams_", "")] = value
        
        if missing_vars:
            raise ValueError(f"Missing required variables in both environment and manifest: {missing_vars}")
        
        # Load optional configuration from environment and manifest
        env_config = {
            "llm_endpoint": os.getenv("LLM_ENDPOINT") or manifest_env.get("LLM_ENDPOINT"),
            "llm_model": os.getenv("LLM_MODEL") or manifest_env.get("LLM_MODEL", "llama3.1"),
            "system_prompt": os.getenv("SYSTEM_PROMPT") or self.manifest.get("system_prompt", ""),
            "summary_interval_minutes": int(os.getenv("SUMMARY_INTERVAL_MINUTES") or manifest_env.get("SUMMARY_INTERVAL_MINUTES", "60")),
            "max_messages": int(os.getenv("MAX_MESSAGES") or manifest_env.get("MAX_MESSAGES", "50")),
            "websocket_url": os.getenv("WEBSOCKET_URL") or manifest_env.get("WEBSOCKET_URL"),
            "websocket_enabled": os.getenv("WEBSOCKET_ENABLED") or manifest_env.get("WEBSOCKET_ENABLED", "false"),
            "webhook_url": os.getenv("MS_TEAMS_WEBHOOK_URL") or manifest_env.get("MS_TEAMS_WEBHOOK_URL"),
            "destination_team_id": os.getenv("MS_TEAMS_DESTINATION_TEAM_ID") or manifest_env.get("MS_TEAMS_DESTINATION_TEAM_ID"),
            "destination_channel_id": os.getenv("MS_TEAMS_DESTINATION_CHANNEL_ID") or manifest_env.get("MS_TEAMS_DESTINATION_CHANNEL_ID")
        }
        
        # Override with WebSocket config from manifest
        websocket_config = self.manifest.get("websocket", {})
        if websocket_config.get("enabled") and websocket_config.get("url"):
            env_config["websocket_enabled"] = "true"
            env_config["websocket_url"] = websocket_config["url"]
        
        config.update(env_config)
        return config
    
    async def test_with_mock_messages(self) -> Dict[str, Any]:
        """Test the workflow with mock messages to verify webhook posting."""
        try:
            logger.info("Starting test workflow with mock messages")
            self.last_run_time = datetime.now().isoformat()
            
            # Create mock messages
            mock_messages = [
                {
                    "id": "test_msg_1",
                    "createdDateTime": "2026-03-05T20:40:00Z",
                    "from": {"user": {"displayName": "John Doe"}},
                    "body": {"content": "Hey team, I just finished the quarterly report. Let me know if you need any changes."}
                },
                {
                    "id": "test_msg_2", 
                    "createdDateTime": "2026-03-05T20:41:00Z",
                    "from": {"user": {"displayName": "Jane Smith"}},
                    "body": {"content": "Great work! I reviewed the numbers and they look good. Can we schedule a meeting to discuss next steps?"}
                },
                {
                    "id": "test_msg_3",
                    "createdDateTime": "2026-03-05T20:42:00Z", 
                    "from": {"user": {"displayName": "Mike Johnson"}},
                    "body": {"content": "I'll send the calendar invite for tomorrow at 2 PM. Also, don't forget about the client presentation on Friday."}
                }
            ]
            
            logger.info("Using mock messages for testing", count=len(mock_messages))
            
            # Generate summary using mock messages
            summary = await self.summarizer.summarize_messages(mock_messages)
            logger.info("Generated summary from mock data", length=len(summary))
            
            # Format the test summary message
            summary_message = f"""🧪 Test Summary (Mock Data)\n\n{summary}\n\n_This is a test summary generated from mock messages to verify webhook functionality._\n\n_Test Status: {self.config.get('webhook_url', 'No webhook URL')}_"""
            
            # Try webhook posting first
            post_result = {"success": False}
            posting_method = "unknown"
            
            if self.config.get("webhook_url"):
                logger.info("Testing webhook posting with mock summary")
                post_result = await self.post_via_webhook(summary_message)
                posting_method = "webhook"
            else:
                logger.error("No webhook URL configured for testing")
                return {"success": False, "error": "No webhook URL configured"}
            
            if post_result["success"]:
                logger.info(f"Successfully posted test summary via {posting_method}")
                return {
                    "success": True,
                    "action": "test_summary_posted",
                    "method": posting_method,
                    "message_count": len(mock_messages),
                    "summary_length": len(summary),
                    "test_mode": True,
                    "last_run_time": self.last_run_time
                }
            else:
                logger.error(f"Failed to post test summary via {posting_method}")
                return {"success": False, "error": f"Failed to post test summary: {post_result.get('error', 'Unknown error')}"}
                
        except Exception as e:
            logger.error("Error in test workflow", error=str(e))
            return {"success": False, "error": str(e)}
    
    async def post_via_webhook(self, message: str) -> Dict[str, Any]:
        """Post message using MS Teams webhook URL."""
        if not self.config.get("webhook_url"):
            logger.error("Webhook URL not configured")
            return {"success": False, "error": "No webhook URL configured"}
        
        if not HAS_HTTP:
            logger.error("HTTP library not available for webhook posting")
            return {"success": False, "error": "HTTP library not available"}
        
        try:
            payload = {
                "@type": "MessageCard",
                "@context": "http://schema.org/extensions",
                "themeColor": "0076D7",
                "summary": "Channel Summary",  
                "sections": [{
                    "activityTitle": "Teams Channel Summary",
                    "text": message,
                    "markdown": True
                }]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.config["webhook_url"],
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info("Successfully posted message via webhook")
                    return {"success": True, "method": "webhook"}
                else:
                    logger.error("Webhook posting failed", 
                               status_code=response.status_code,
                               response_text=response.text)
                    return {"success": False, "error": f"HTTP {response.status_code}"}
                    
        except Exception as e:
            logger.error("Error posting via webhook", error=str(e))
            return {"success": False, "error": str(e)}
    
    async def run_summarization(self) -> Dict[str, Any]:
        """Main workflow: read messages, summarize, and post back to channel."""
        try:
            logger.info("Starting message summarization workflow")
            self.last_run_time = datetime.now().isoformat()
            
            # Step 1: Read messages from channel
            messages_result = await read_channel_messages_tool(
                team_id=self.config["team_id"],
                channel_id=self.config["channel_id"],
                tenant_id=self.config["tenant_id"],
                client_id=self.config["client_id"],
                client_secret=self.config["client_secret"],
                since_minutes=self.config["summary_interval_minutes"],
                max_messages=self.config["max_messages"]
            )
            
            if not messages_result["success"]:
                logger.error("Failed to read messages from channel")
                return {"success": False, "error": "Failed to read messages"}
            
            messages = messages_result["messages"]
            logger.info("Retrieved messages for summarization", count=len(messages))
            
            # Step 2: Generate summary
            if len(messages) == 0:
                logger.info("No new messages to summarize")
                return {
                    "success": True, 
                    "action": "no_messages", 
                    "message_count": 0,
                    "last_run_time": self.last_run_time
                }
            
            summary = await self.summarizer.summarize_messages(messages)
            logger.info("Generated summary", length=len(summary))
            
            # Step 3: Post summary back to channel (source or destination)
            # Use destination channel if configured, otherwise use source channel
            post_team_id = self.config.get("destination_team_id") or self.config["team_id"]
            post_channel_id = self.config.get("destination_channel_id") or self.config["channel_id"]
            
            summary_message = f"""🤖 Automated Channel Summary\n\n{summary}\n\n_This summary covers the last {self.config['summary_interval_minutes']} minutes of channel activity._"""
            
            # Try webhook posting first if configured, then fallback to Graph API
            post_result = {"success": False}
            posting_method = "unknown"
            
            if self.config.get("webhook_url"):
                logger.info("Attempting to post summary via webhook")
                post_result = await self.post_via_webhook(summary_message)
                posting_method = "webhook"
            
            # Fallback to Graph API if webhook failed or not configured  
            if not post_result["success"]:
                if self.config.get("webhook_url"):
                    logger.info("Webhook posting failed, falling back to Graph API")
                else:
                    logger.info("No webhook configured, using Graph API")
                
                posting_method = "graph_api"
                post_result = await post_channel_message_tool(
                    team_id=post_team_id,
                    channel_id=post_channel_id,
                    tenant_id=self.config["tenant_id"],
                    client_id=self.config["client_id"],
                    client_secret=self.config["client_secret"],
                    message=summary_message,
                    importance="normal"
                )
            
            # Log whether posting to same or different channel
            is_different_channel = (post_team_id != self.config["team_id"] or 
                                  post_channel_id != self.config["channel_id"])
            destination_info = "destination" if is_different_channel else "source"
            
            if post_result["success"]:
                logger.info(f"Successfully posted summary to {destination_info} channel using {posting_method}", 
                           message_id=post_result.get("message_id", "N/A"),
                           messages_summarized=len(messages),
                           post_team_id=post_team_id,
                           post_channel_id=post_channel_id,
                           method=posting_method)
                return {
                    "success": True,
                    "action": "summary_posted",
                    "method": posting_method,
                    "message_count": len(messages),
                    "summary_length": len(summary),
                    "posted_message_id": post_result.get("message_id", "N/A"),
                    "last_run_time": self.last_run_time
                }
            else:
                logger.error(f"Failed to post summary to channel using {posting_method}", 
                           error=post_result.get("error", "Unknown error"))
                return {"success": False, "error": f"Failed to post summary via {posting_method}: {post_result.get('error', 'Unknown error')}"}
                
        except Exception as e:
            logger.error("Error in summarization workflow", error=str(e))
            return {"success": False, "error": str(e)}
    
    async def run_with_websocket(self):
        """Run the agent in WebSocket mode with real-time capabilities."""
        if not self.websocket_client:
            logger.error("WebSocket client not initialized")
            return
        
        logger.info("Starting agent in WebSocket mode")
        
        # Start WebSocket client in background
        websocket_task = asyncio.create_task(self.websocket_client.connect_and_listen())
        
        # Also run periodic summarization (optional)
        if self.config.get("summary_interval_minutes", 0) > 0:
            periodic_task = asyncio.create_task(self._periodic_summarization())
            
            try:
                # Wait for either task to complete (or fail)
                done, pending = await asyncio.wait(
                    [websocket_task, periodic_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel remaining tasks
                for task in pending:
                    task.cancel()
                    
            except KeyboardInterrupt:
                logger.info("Received interrupt, shutting down")
                self.websocket_client.stop()
                websocket_task.cancel()
                periodic_task.cancel()
        else:
            try:
                await websocket_task
            except KeyboardInterrupt:
                logger.info("Received interrupt, shutting down WebSocket")
                self.websocket_client.stop()
                websocket_task.cancel()
    
    async def _periodic_summarization(self):
        """Run periodic summarization in background."""
        interval_seconds = self.config["summary_interval_minutes"] * 60
        logger.info("Starting periodic summarization", interval_minutes=self.config["summary_interval_minutes"])
        
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                logger.info("Running scheduled summarization")
                result = await self.run_summarization()
                logger.info("Scheduled summarization completed", success=result.get("success"))
            except asyncio.CancelledError:
                logger.info("Periodic summarization cancelled")
                break
            except Exception as e:
                logger.error("Error in periodic summarization", error=str(e))

async def main():
    """Main entry point for the agent."""
    logger.info("MS Teams Channel Summarizer Agent starting")
    
    # Initialize the summarizer
    try:
        agent = TeamsChannelSummarizer()
        
        # Check if WebSocket mode is enabled
        websocket_enabled = agent.config.get("websocket_enabled", "false").lower() == "true"
        
        # Check for command line arguments or environment variable for mode
        import sys
        use_websocket = False
        
        if len(sys.argv) > 1:
            if sys.argv[1] == "--websocket" or sys.argv[1] == "-w":
                use_websocket = True
            elif sys.argv[1] == "--test" or sys.argv[1] == "-t":
                # Test mode - use mock messages to test webhook posting
                logger.info("Running in test mode with mock messages")
                result = await agent.test_with_mock_messages()
                print(json.dumps(result, indent=2))
                if result["success"]:
                    logger.info("Test mode execution completed successfully")
                else:
                    logger.error("Test mode execution failed", error=result.get("error"))
                    exit(1)
                return
            elif sys.argv[1] == "--help" or sys.argv[1] == "-h":
                print("MS Teams Channel Summarizer Agent")
                print("Usage:")
                print("  python agent.py           # Run once and exit")
                print("  python agent.py -t        # Run in test mode with mock messages")
                print("  python agent.py --test    # Run in test mode with mock messages")
                print("  python agent.py -w        # Run in WebSocket mode")
                print("  python agent.py --websocket  # Run in WebSocket mode")
                return
        
        # Auto-enable WebSocket if configured in manifest
        if websocket_enabled and not use_websocket:
            logger.info("WebSocket enabled in configuration, starting WebSocket mode")
            use_websocket = True
        
        if use_websocket and agent.websocket_client:
            # Run in WebSocket mode with real-time capabilities
            logger.info("Starting in WebSocket mode")
            await agent.run_with_websocket()
        else:
            # Run single summarization and exit
            logger.info("Running single summarization")
            result = await agent.run_summarization()
            
            # Print result for AgentFlow framework
            print(json.dumps(result, indent=2))
            
            if result["success"]:
                logger.info("Agent execution completed successfully")
            else:
                logger.error("Agent execution failed", error=result.get("error"))
                exit(1)
            
    except Exception as e:
        logger.error("Critical error in agent execution", error=str(e))
        print(json.dumps({"success": False, "error": str(e)}, indent=2))
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())