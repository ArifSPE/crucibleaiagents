"""
    MS Team Integration tool
    Provide functions to interact with MS Teams API, such as fetching channel messages and posting summaries.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import structlog
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from urllib.parse import quote

try:
    import msal
    import httpx
except ImportError:
    msal = None
    httpx = None

logger = structlog.get_logger(__name__)

@dataclass
class MSTeamsConfig:
    """MSTeam Authentication and API configuration."""
    tenant_id: str
    client_id: str
    client_secret: str
    team_id: str
    channel_id: str
    scopes: List[str] = None

    def __post_init__(self):
        if self.scopes is None:
            self.scopes = ["https://graph.microsoft.com/.default"]

@dataclass
class ChannelMessage:
    """Represents a message in an MS Teams channel."""
    id: str
    created_datetime: datetime
    from_user: str
    from_user_id: str
    body_content: str
    importance: str = "normal"
    attachments: List[Dict[str, Any]] = None
    reactions: List[Dict[str, Any]] = None
    reply_count: int = 0

    def __post_init__(self):
        if self.attachments is None:
            self.attachments = []
        if self.reactions is None:
            self.reactions = [] 


class MSTeamClient:
    """Client for interacting with Microsoft Graph API 
    to fetch channel messages and post summaries.
    Features:
    - OAuth2 authentication with MSAL
    - Read Channel Messages with filtering
    - Post summary messages to channel
    - Handle Rate limits and pagination
    - Async support for concurrent operations
    """

    GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"
    AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{}"

    def __init__(self, config: MSTeamsConfig):
        if msal is None or httpx is None:
            raise ImportError("msal and httpx libraries are required for MSTeamClient")
        self.config = config
        self.authority = self.AUTHORITY_TEMPLATE.format(config.tenant_id)
        self.app = msal.ConfidentialClientApplication(
            client_id=config.client_id,
            client_credential=config.client_secret,
            authority=self.authority
        )
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

        logger.info("MSTeamClient initialized", 
                    team_id=config.team_id, channel_id=config.channel_id)  

    async def _get_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        if self._access_token and self._token_expiry and datetime.utcnow() < self._token_expiry - timedelta(minutes=5):
            return self._access_token
        
        logger.info("Acquiring new access token from MSAL")
        result = self.app.acquire_token_for_client(scopes=self.config.scopes)
        
        if "access_token" in result:
            self._access_token = result["access_token"]
            expires_in = result.get("expires_in", 3600)
            self._token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
            logger.info("Access token acquired", expires_in=expires_in)
            return self._access_token
        else:
            error_msg = f"Failed to acquire access token: {result.get('error_description', 'Unknown error')}"
            logger.error(error_msg)
            raise Exception(error_msg)  
        
    async def _make_request(
            self,
            method: str,
            url: str,
            json_data: Optional[dict] = None,
            params: Optional[dict] = None,
            retries: int = 3,
    ) -> Dict[str, Any]:
        """Make an authenticated request to the Graph API with retry logic."""
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        for attempt in range(1, retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        json=json_data,
                        params=params,
                        timeout=10
                    )
                if response.status_code == 429:  # Rate limit
                    retry_after = int(response.headers.get("Retry-After", "60"))
                    logger.warning("Rate limited by Graph API, retrying after delay", retry_after=retry_after, attempt=attempt)
                    await asyncio.sleep(retry_after)
                elif response.status_code >= 500:  # Server error
                    logger.warning("Server error from Graph API, retrying", status_code=response.status_code, attempt=attempt)
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                elif response.status_code >= 400:  # Client error
                    logger.error("Client error from Graph API", status_code=response.status_code, 
                               response_text=response.text[:500], url=url)
                    response.raise_for_status()  # This will raise the exception with details
                else:
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPError as e:
                logger.error("HTTP error during Graph API request", error=str(e), attempt=attempt)
                if attempt == retries:
                    raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff

        raise Exception("Failed to make request after retries")

    async def read_channel_messages(
            self,
            team_id: Optional[str] = None,
            channel_id: Optional[str] = None,
            since_minutes: Optional[int] = 50,
            max_messages: Optional[int] = 50,
            filter_bot_messages: bool = True
    ) -> List[ChannelMessage]:
        """Fetch messages from a channel with optional filtering.
        
        Args:
            team_id: The ID of the team to fetch messages from. Defaults to the configured team ID.
            channel_id: The ID of the channel to fetch messages from. Defaults to the configured channel ID.
            since_minutes: Fetch messages created within the last `since_minutes` minutes. Defaults to 50.
            max_messages: The maximum number of messages to fetch. Defaults to 50.
            filter_bot_messages: Whether to filter out messages from bots. Defaults to True.
        
        Returns:
            A list of ChannelMessage objects.
        """
        logger.info("Fetching channel messages", 
                    team_id=team_id, 
                    channel_id=channel_id, 
                    since_minutes=since_minutes,
                      max_messages=max_messages, 
                      filter_bot_messages=filter_bot_messages)
        #Calculate the timestamp for filtering messages
        since_datetime = datetime.now(tz=timezone.utc) - timedelta(minutes=since_minutes)

        # Build Graph URL with proper encoding
        # For Teams, we need to be more careful with channel ID encoding
        team_id_to_use = team_id or self.config.team_id
        channel_id_to_use = channel_id or self.config.channel_id
        
        # Teams channel IDs need standard URL encoding
        team_id_encoded = quote(team_id_to_use, safe='')
        channel_id_encoded = quote(channel_id_to_use, safe='')
        
        url = f"{self.GRAPH_API_ENDPOINT}/teams/{team_id_encoded}/channels/{channel_id_encoded}/messages"
        
        logger.info("Constructed Graph API URL for channel messages", 
                   team_id=team_id_to_use, channel_id=channel_id_to_use)

        # Graph API for Team channel does not supports $filtering or $orderby, 
        # so we will fetch messages and filter/sort client side
        # Note: Teams channel messages API has a maximum limit of 50 messages per request

        params = {
            "$top": min(max_messages, 50)  # Teams API limit is 50 messages per request
        }

        try:
            response = await self._make_request("GET", url, params=params)
            
            # Add debugging info
            if response is None:
                logger.error("Received None response from Graph API")
                raise Exception("Graph API returned None response")
            
            if not isinstance(response, dict):
                logger.error("Received non-dict response from Graph API", response_type=type(response))
                raise Exception(f"Graph API returned unexpected response type: {type(response)}")
            
            messages_data = response.get("value", [])
            
            if messages_data is None:
                logger.warning("Messages data is None, no messages found")
                messages_data = []  

            messages = []
            for msg_data in messages_data:
                # Skip if message data is invalid
                if not msg_data or not isinstance(msg_data, dict):
                    continue
                    
                #Parse Message
                from_data = msg_data.get("from", {})
                user_data = from_data.get("user", {}) if from_data else {}

                # Skip bot messages if filtering is enabled and user_data exists
                if filter_bot_messages and user_data and user_data.get("userType") == "bot":
                    continue  # Skip bot messages  

                body_data = msg_data.get("body", {})
                
                # Handle missing createdDateTime field
                created_datetime_str = msg_data.get("createdDateTime")
                if not created_datetime_str:
                    continue  # Skip messages without timestamp
                
                try:
                    created_datetime = datetime.fromisoformat(created_datetime_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError) as e:
                    logger.warning("Invalid datetime format in message", datetime_str=created_datetime_str, error=str(e))
                    continue  # Skip messages with invalid datetime

                #create ChannelMessage object
                message = ChannelMessage(
                    id=msg_data.get("id"),
                    created_datetime=created_datetime,
                    from_user=user_data.get("displayName", "Unknown") if user_data else "Unknown",
                    from_user_id=user_data.get("id", "Unknown") if user_data else "Unknown",
                    body_content=body_data.get("content", ""),
                    importance=msg_data.get("importance", "normal"),
                    attachments=msg_data.get("attachments", []),
                    reactions=msg_data.get("reactions", []),
                    reply_count=msg_data.get("replyCount", 0)
                )

                messages.append(message)

            # Filter messages based on time (client side filtering since Graph API does not support it for channel messages)
            if since_minutes:
                messages = [msg for msg in messages if msg.created_datetime >= since_datetime]
            
            messages = messages[:max_messages]  # Limit to requested number
            logger.info("Successfully read messages from channel", 
                        count=len(messages), 
                        since=since_datetime.isoformat())
            return messages
        except Exception as e:
            logger.error("Error fetching channel messages", error=str(e))
            raise

    async def post_channel_message(
            self,
            team_id: Optional[str] = None,
            channel_id: Optional[str] = None,
            message: str = "",
            importance: str = "normal",
            content_type: str = "html",
    ) -> Dict[str, Any]:
        """Post a message to a channel.
        
        Args:
            team_id: The ID of the team to post the message to. Defaults to the configured team ID.
            channel_id: The ID of the channel to post the message to. Defaults to the configured channel ID.
            message: The content of the message to post.
            importance: The importance level of the message (normal, high, low). Defaults to "normal".
            content_type: The content type of the message body (html or text). Defaults to "html".
        
        Returns:
            The response from the Graph API as a dictionary.
        """
        logger.info("Posting message to channel", 
                    team_id=team_id, 
                    channel_id=channel_id, 
                    importance=importance)
        team_id_encoded = quote(team_id or self.config.team_id, safe='')
        channel_id_encoded = quote(channel_id or self.config.channel_id, safe='')
        url = f"{self.GRAPH_API_ENDPOINT}/teams/{team_id_encoded}/channels/{channel_id_encoded}/messages"
        payload = {
            "body": {
                "contentType": content_type,
                "content": message
            },
            "importance": importance
        }
        try:
            response = await self._make_request("POST", url, json_data=payload)
            logger.info("Successfully posted message to channel", message_id=response.get("id"))
            return response
        except Exception as e:
            logger.error("Error posting message to channel", error=str(e))
            raise
    
    async def get_team_info(self, team_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch information about the team."""
        team_id_encoded = quote(team_id or self.config.team_id, safe='')
        url = f"{self.GRAPH_API_ENDPOINT}/teams/{team_id_encoded}"
        try:
            response = await self._make_request("GET", url)
            logger.info("Successfully fetched team info", team_id=team_id or self.config.team_id)
            return response
        except Exception as e:
            logger.error("Error fetching team info", error=str(e))
            raise
    
    async def get_channel_info(self, team_id: Optional[str] = None, channel_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch information about the channel."""
        team_id_encoded = quote(team_id or self.config.team_id, safe='')
        channel_id_encoded = quote(channel_id or self.config.channel_id, safe='')
        url = f"{self.GRAPH_API_ENDPOINT}/teams/{team_id_encoded}/channels/{channel_id_encoded}"
        try:
            response = await self._make_request("GET", url)
            logger.info("Successfully fetched channel info", channel_id=channel_id or self.config.channel_id)
            return response
        except Exception as e:
            logger.error("Error fetching channel info", error=str(e))
            raise

# Tool functions wrapper for agent integration
async def read_channel_messages_tool(
        team_id: str,
        channel_id: str,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        since_minutes: Optional[int] = 60,
        max_messages: Optional[int] = 50,
        **kwargs
) -> Dict[str, Any]:
    """Tool function to read channel messages for agent use."""
    config = MSTeamsConfig(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        team_id=team_id,
        channel_id=channel_id
    )
    client = MSTeamClient(config=config)

    messages = await client.read_channel_messages(
        team_id=team_id,
        channel_id=channel_id,
        since_minutes=since_minutes,
        max_messages=max_messages,
        filter_bot_messages=True
    )
    
    return {
       "success": True,
       "message_count": len(messages),
       "messages": [{
           "id": msg.id,
           "from": msg.from_user,
           "content": msg.body_content,
           "created_datetime": msg.created_datetime.isoformat(),
           "importance": msg.importance,
           "reactions": msg.reactions,
       } for msg in messages]
   }

async def post_channel_message_tool(
        team_id: str,
        channel_id: str,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        message: str,
        importance: str = "normal",
        **kwargs
) -> Dict[str, Any]:
    """Tool function to post a message to a channel for agent use."""
    config = MSTeamsConfig(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        team_id=team_id,
        channel_id=channel_id
    )
    client = MSTeamClient(config=config)

    response = await client.post_channel_message(
        team_id=team_id,
        channel_id=channel_id,
        message=message,
        importance=importance
    )
    return {
        "success": True,
        "message_id": response.get("id"),
        "posted_datetime": response.get("createdDateTime"),
        "web_url": response.get("webUrl")
    }   
