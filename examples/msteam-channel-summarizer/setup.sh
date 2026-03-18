#!/bin/bash
# Quick Setup Script for MS Teams Channel Summarizer Agent

echo "🚀 MS Teams Channel Summarizer - Quick Setup"
echo "=============================================="

# Check if we're in the right directory
if [ ! -f "src/agent.py" ]; then
    echo "❌ Please run this script from the msteam-channel-summarizer directory"
    exit 1
fi

echo ""
echo "📋 Setup Options:"
echo "1. 🧪 Test Mode (Mock MS Teams Integration)"  
echo "2. 🔧 Development Mode (Set up environment variables)"
echo "3. ⚡ Quick Demo (Run with sample data)"
echo ""

read -p "Choose an option (1-3): " choice

case $choice in
    1)
        echo ""
        echo "🧪 Running in Test Mode..."
        echo "This will test all functionality with mock MS Teams data"
        python test_agent.py
        ;;
    2)
        echo ""
        echo "🔧 Setting up Development Environment..."
        echo ""
        echo "You'll need MS Teams App Registration credentials:"
        echo "1. Go to Azure Portal > App Registrations"
        echo "2. Create a new app registration"  
        echo "3. Add Microsoft Graph API permissions (Chat.Read, Channel.ReadWrite)"
        echo "4. Get Tenant ID, Client ID, and Client Secret"
        echo ""
        
        # Create a .env file
        echo "Creating .env file template..."
        cat > .env << 'EOF'
# MS Teams Configuration - REQUIRED
MS_TEAMS_TENANT_ID=your-tenant-id-here
MS_TEAMS_CLIENT_ID=your-client-id-here
MS_TEAMS_CLIENT_SECRET=your-client-secret-here
MS_TEAMS_TEAM_ID=your-team-id-here
MS_TEAMS_CHANNEL_ID=your-channel-id-here

# Optional: Separate destination channel
# MS_TEAMS_DESTINATION_TEAM_ID=destination-team-id
# MS_TEAMS_DESTINATION_CHANNEL_ID=destination-channel-id

# Optional: LLM Integration
# LLM_ENDPOINT=http://localhost:11434
# LLM_MODEL=llama3.1

# Optional: WebSocket Control
# WEBSOCKET_URL=ws://localhost:8080/ws
# WEBSOCKET_ENABLED=true
EOF
        
        echo ""
        echo "✅ Created .env file template"
        echo "📝 Edit the .env file with your MS Teams credentials"
        echo ""
        echo "To run with environment variables:"
        echo "   source .env && python src/agent.py"
        ;;
    3)
        echo ""
        echo "⚡ Quick Demo Mode..."
        echo "Running agent with mock configuration for demonstration"
        
        # Set temporary test environment variables  
        export MS_TEAMS_TENANT_ID="demo-tenant-12345"
        export MS_TEAMS_CLIENT_ID="demo-client-67890" 
        export MS_TEAMS_CLIENT_SECRET="demo-secret-abcdef"
        export MS_TEAMS_TEAM_ID="demo-team-98765"
        export MS_TEAMS_CHANNEL_ID="demo-channel-54321"
        
        echo ""
        echo "🤖 Starting Agent Demo (will use mock MS Teams integration)..."
        echo "Note: This is for demonstration - no real Teams messages will be processed"
        
        # Test the configuration loading
        python -c "
import sys, os
sys.path.insert(0, 'src')
from agent import TeamsChannelSummarizer
try:
    agent = TeamsChannelSummarizer()
    print('✅ Agent initialized successfully with demo configuration')
    print(f'   Team ID: {agent.config[\"team_id\"]}')
    print(f'   Channel ID: {agent.config[\"channel_id\"]}')
    print('   Status: Ready for deployment with real credentials')
except Exception as e:
    print(f'❌ Demo failed: {e}')
"
        ;;
    *)
        echo "❌ Invalid option selected"
        exit 1
        ;;
esac

echo ""
echo "📚 Additional Resources:"
echo "• Test Suite: python test_agent.py" 
echo "• Destination Channel Tests: python test_destination_channels.py"
echo "• WebSocket Testing: python websocket_tester.py"
echo "• Documentation: README.md"
echo ""
echo "🎉 Setup complete!"