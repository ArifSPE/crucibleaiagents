import os
import logging
from pathlib import Path


def _get_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

def get_package_root() -> Path:
    if os.path.exists('/package'):
        return Path('/package')
    else:
        api_dir = Path(__file__).parent.resolve()
        return api_dir.parent / "package"
    

PACKAGE_ROOT = get_package_root()
STORAGE_DIR = os.getenv('STORAGE_DIR', str(PACKAGE_ROOT / 'deployed'))
ARCHIVE_DIR = os.getenv('ARCHIVE_DIR', str(PACKAGE_ROOT / 'archive'))
os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

logger = logging.getLogger("crucibleaiagents.api")
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s')    

ALLOWED_LLM_PROVIDERS = {
    "local_ollama",
    "ollama_cloud",
    "ibm_watson",
    "aws_bedrock",
    "anthropic",
    "claude",
}

# Provider-specific credential templates
LLM_PROVIDER_CREDENTIAL_TEMPLATES = {
    "local_ollama": [],  # No credentials needed
    "ollama_cloud": ["api_key"],
    "ibm_watson": ["api_key", "instance_id"],
    "aws_bedrock": ["access_key_id", "secret_access_key", "region"],
    "anthropic": ["api_key"],
    "claude": ["api_key"],
}

_CORS_ORIGINS_DEFAULT = ",".join([
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
])

LLM_CHAT_MEMORY_TTL_HOURS = int(os.getenv("LLM_CHAT_MEMORY_TTL_HOURS", "168"))
LLM_CHAT_MEMORY_MAX_TURNS = int(os.getenv("LLM_CHAT_MEMORY_MAX_TURNS", "20"))
LLM_CHAT_MEMORY_READ_LIMIT_DEFAULT = int(os.getenv("LLM_CHAT_MEMORY_READ_LIMIT_DEFAULT", "100"))
LLM_CHAT_MEMORY_READ_LIMIT_MAX = int(os.getenv("LLM_CHAT_MEMORY_READ_LIMIT_MAX", "500"))
LLM_CHAT_MEMORY_SUMMARIZATION_ENABLED = _get_bool_env("LLM_CHAT_MEMORY_SUMMARIZATION_ENABLED", True)
LLM_CHAT_MEMORY_SUMMARIZATION_TRIGGER_TURNS = int(os.getenv("LLM_CHAT_MEMORY_SUMMARIZATION_TRIGGER_TURNS", "8"))
LLM_CHAT_MEMORY_SUMMARY_INPUT_MAX_MESSAGES = int(os.getenv("LLM_CHAT_MEMORY_SUMMARY_INPUT_MAX_MESSAGES", "40"))

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://mcp_server:9001/mcp")
MCP_CLIENT_TIMEOUT_SECONDS = int(os.getenv("MCP_CLIENT_TIMEOUT_SECONDS", "20"))
MCP_SERVER_AUTH_TOKEN = os.getenv("MCP_SERVER_AUTH_TOKEN", "").strip()
MCP_CLIENT_ORCHESTRATION = os.getenv("MCP_CLIENT_ORCHESTRATION", "auto").strip().lower()
MCP_CHAT_TOOLING_ENABLED = _get_bool_env("MCP_CHAT_TOOLING_ENABLED", False)
MCP_CHAT_TOOLING_MAX_TOOLS = int(os.getenv("MCP_CHAT_TOOLING_MAX_TOOLS", "3"))
MCP_CHAT_TOOLING_MAX_RESULT_CHARS = int(os.getenv("MCP_CHAT_TOOLING_MAX_RESULT_CHARS", "4000"))
