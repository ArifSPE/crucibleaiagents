import os
import logging
from pathlib import Path

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
