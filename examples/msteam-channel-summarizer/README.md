# MS Teams Channel Summarizer Agent

An intelligent agent that automatically reads messages from MS Teams channels, generates AI-powered summaries, and posts them back to the channel. Perfect for keeping track of active discussions and ensuring important information doesn't get missed.

## Features

- 🔍 **Smart Message Reading**: Fetches messages from configured Teams channels with time-based filtering
- 🤖 **AI-Powered Summarization**: Uses LLM (Ollama, OpenAI, etc.) for intelligent message summarization  
- 📝 **Automated Posting**: Posts formatted summaries back to the Teams channel
- ⏰ **Scheduled Execution**: Configurable interval-based summarization (hourly, daily, etc.)
- 🌐 **Webhook Support**: Trigger summarization via HTTP webhooks
- � **WebSocket Integration**: Real-time message processing and control
- �🔄 **Fallback Mode**: Simple rule-based summarization when LLM unavailable
- 🛡️ **Error Handling**: Robust error handling with rate limiting and retries

## Prerequisites

### 1. Azure AD App Registration

Create an Azure AD application with Teams API permissions:

1. Go to [Azure Portal](https://portal.azure.com) → Azure Active Directory → App registrations
2. Click "New registration"
3. Configure your app:
   - **Name**: `Teams Channel Summarizer`
   - **Account types**: Accounts in this organizational directory only
   - **Redirect URI**: Not required for this use case
4. Note the **Application (client) ID** and **Directory (tenant) ID**
5. Create a client secret in "Certificates & secrets"
6. Configure API permissions in "API permissions":
   - Add Microsoft Graph permissions:
     - `ChannelMessage.Read.All` (Read all channel messages)
     - `ChannelMessage.Send` (Send channel messages)
   - Grant admin consent for your organization

### 2. Teams Channel Information

Get your Teams channel details:

#### Source Channel (where messages are read from)
1. Open MS Teams in web browser
2. Navigate to your source channel
3. Copy the Team ID and Channel ID from the URL:
   ```
   https://teams.microsoft.com/l/channel/{CHANNEL_ID}/General?groupId={TEAM_ID}
   ```

#### Destination Channel (where summaries are posted) - Optional
1. If you want summaries posted to a different channel, repeat the process above
2. Use `MS_TEAMS_DESTINATION_TEAM_ID` and `MS_TEAMS_DESTINATION_CHANNEL_ID` 
3. If not specified, summaries will be posted to the same channel messages are read from

### 3. LLM Backend (Optional)

For enhanced summarization, set up an LLM:

- **Ollama**: Install locally and run `ollama serve`
- **OpenAI**: Get API key and modify agent for OpenAI integration
- **Other**: Any compatible LLM API endpoint

## Configuration

### Environment Variables

Configure the agent using these environment variables:

```bash
# Required: MS Teams Configuration
MS_TEAMS_TENANT_ID=your-tenant-id-here
MS_TEAMS_CLIENT_ID=your-client-id-here  
MS_TEAMS_CLIENT_SECRET=your-client-secret-here
MS_TEAMS_TEAM_ID=your-team-id-here
MS_TEAMS_CHANNEL_ID=your-channel-id-here

# Optional: LLM Configuration
LLM_ENDPOINT=http://localhost:11434  # Ollama default
LLM_MODEL=llama3.1                   # Model name

# Optional: Agent Behavior
SUMMARY_INTERVAL_MINUTES=60          # How far back to look for messages
MAX_MESSAGES=50                      # Maximum messages to summarize

# Optional: WebSocket Configuration
WEBSOCKET_URL=ws://localhost:8080/ws/teams-channel  # WebSocket endpoint
WEBSOCKET_ENABLED=true               # Enable real-time WebSocket integration
```

### Manifest Configuration

Update the `manifest.json` file with your specific values:

```json
{
  "environment": {
    "MS_TEAMS_TENANT_ID": "your-actual-tenant-id",
    "MS_TEAMS_CLIENT_ID": "your-actual-client-id",
    "MS_TEAMS_CLIENT_SECRET": "your-actual-client-secret",
    "MS_TEAMS_TEAM_ID": "your-actual-source-team-id", 
    "MS_TEAMS_CHANNEL_ID": "your-actual-source-channel-id",
    "MS_TEAMS_DESTINATION_TEAM_ID": "your-actual-destination-team-id",
    "MS_TEAMS_DESTINATION_CHANNEL_ID": "your-actual-destination-channel-id"
  }
}
```

**Note:** Destination team and channel are optional. If not specified, summaries will be posted to the same channel where messages are read from.

## Usage

### 1. Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MS_TEAMS_TENANT_ID="your-tenant-id"
export MS_TEAMS_CLIENT_ID="your-client-id"
# ... other variables

# Run the agent
python src/agent.py
```

### 2. AgentFlow Integration

1. Package the agent:
   ```bash
   zip -r msteam-summarizer.zip . -x "*.git*" "__pycache__/*" "*.pyc"
   ```

2. Upload via AgentFlow UI at `http://localhost:3000`

3. Configure environment variables in the UI

4. Enable scheduling for automatic execution

### 3. Webhook Triggers

Send POST request to trigger summarization:

```bash
curl -X POST http://your-agentflow-instance/webhook/teams \
  -H "Content-Type: application/json" \
  -d '{"trigger": "manual_summary"}'
```

### 4. WebSocket Integration

The agent supports real-time WebSocket communication for interactive control:

#### Starting WebSocket Mode
```bash
# Run agent in WebSocket mode
python src/agent.py --websocket

# Or enable in manifest.json
{
  "websocket": {
    "enabled": true,
    "url": "ws://localhost:8080/ws/teams-channel"
  }
}
```

#### WebSocket Message Types
- **summarize_request**: Trigger immediate summarization
- **status_request**: Get agent status and last run info
- **ping/pong**: Connection health check
- **channel_message**: Real-time message notifications

#### Example WebSocket Messages
```javascript
// Trigger summarization
{
  "type": "summarize_request",
  "request_id": "summary_123",
  "timestamp": "2024-03-05T14:30:00Z"
}

// Get agent status  
{
  "type": "status_request",
  "request_id": "status_456"
}

// Ping for connectivity
{
  "type": "ping"
}
```

#### Testing WebSocket Integration
```bash
# Run interactive WebSocket tester
python websocket_tester.py --interactive

# Run automated WebSocket tests
python websocket_tester.py
```

## Output Examples

### Simple Summarization (No LLM)
```
📊 **Channel Activity Summary** (15 messages)

**Active participants:** Alice Johnson, Bob Smith, Carol Davis

**Key discussions:**
• **Alice Johnson** (7 messages): Working on the quarterly report, need feedback on draft...
• **Bob Smith** (5 messages): Budget meeting scheduled for tomorrow at 2 PM...
• **Carol Davis** (3 messages): New client requirements came in, priority level high...

_Summary generated at 2024-03-05 14:30:00_
```

### LLM-Enhanced Summarization
```
🤖 **Automated Channel Summary**

**Main Topics**: Quarterly report preparation, budget meeting planning, new client requirements
**Participants**: Alice (lead), Bob (finance), Carol (client relations), Mike (technical)  
**Key Points**: Q4 report draft ready for review, budget meeting moved to Tuesday 2 PM
**Action Items**: Review report by Friday, prepare budget projections, contact new client
**Activity Level**: High engagement with 15 messages from 4 team members

_This summary covers the last 60 minutes of channel activity._
```

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   MS Teams      │    │   Agent         │    │   LLM Service   │
│   Channel       │◄──►│   Summarizer    │◄──►│   (Optional)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
    ┌─────────┐            ┌─────────┐              ┌─────────┐
    │ Read    │            │ Process │              │ Generate│
    │Messages │            │& Filter │              │Summary  │
    └─────────┘            └─────────┘              └─────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                       ┌─────────────────┐
                       │   Post Summary  │
                       │   to Channel    │
                       └─────────────────┘
```

## Troubleshooting

### Authentication Issues
- Verify Azure AD app permissions are granted
- Check tenant ID, client ID, and secret are correct
- Ensure the app has consent for your organization

### Message Reading Issues  
- Verify team and channel IDs are correct
- Check that the app has been added to the team
- Ensure `ChannelMessage.Read.All` permission is granted

### LLM Connection Issues
- Verify LLM endpoint is accessible
- Check model name is correct for your LLM service
- Agent will fall back to simple summarization if LLM fails

### Rate Limiting
- Agent includes built-in retry logic with exponential backoff
- Adjust `SUMMARY_INTERVAL_MINUTES` to reduce API calls if needed

## Security Considerations

- Store client secrets securely (use environment variables or key vault)
- Limit Azure AD app permissions to minimum required
- Consider using managed identity for production deployments  
- Review message content filtering for sensitive information
- Implement proper logging without exposing credentials

## Customization

### Adding Custom Summarization Logic

Modify the `MessageSummarizer` class in `src/agent.py`:

```python
def _custom_summarize(self, messages):
    # Your custom summarization logic
    return "Custom summary format"
```

### Integrating Different LLM Providers

Update the `_llm_summarize` method for different APIs:

```python
# OpenAI integration example
import openai
async def _openai_summarize(self, messages):
    # OpenAI API call
    pass
```

### Adding Webhook Endpoints

Extend the agent with FastAPI for webhook support:

```python
from fastapi import FastAPI
app = FastAPI()

@app.post("/webhook/teams")
async def trigger_summary():
    # Trigger summarization
    pass
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License. See LICENSE file for details.