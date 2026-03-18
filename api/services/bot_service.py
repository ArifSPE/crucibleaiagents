import os
import json
import zipfile
import tempfile
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from utils.secrets_manager import get_secrets_manager
from utils.config import ARCHIVE_DIR as ARCHIVES_DIR, STORAGE_DIR


def _tool_catalog() -> List[Dict[str, Any]]:
    """Return stable tool catalog metadata for bot recommendations and UI."""
    return [
        {
            "key": "shell.command",
            "name": "Execute Shell Command",
            "description": "Run allowlisted shell commands with timeout and audit logs.",
            "credential_requirements": [],
            "execution_policy": {"timeout_seconds": 60, "allowlist": True},
        },
        {
            "key": "shell.script",
            "name": "Execute Shell Script",
            "description": "Run short scripts under sandbox constraints.",
            "credential_requirements": [],
            "execution_policy": {"timeout_seconds": 60, "sandboxed": True},
        },
        {
            "key": "rest.call",
            "name": "Call REST Endpoint",
            "description": "Call external/internal APIs using host allowlists and retries.",
            "credential_requirements": ["api_token"],
            "execution_policy": {"timeout_seconds": 30, "max_retries": 2, "host_allowlist": True},
        },
    ]


def _recommend_tools_for_conversation(user_interests_goals: str, bot_type: str) -> List[Dict[str, Any]]:
    """Rule-based recommendation with clear output schema for conversational bot builder."""
    catalog = _tool_catalog()

    text = f"{user_interests_goals} {bot_type}".lower()
    selected_keys: List[str] = []

    if any(token in text for token in ["ops", "devops", "terminal", "shell", "automation"]):
        selected_keys.append("shell.command")
    if any(token in text for token in ["batch", "script", "workflow"]):
        selected_keys.append("shell.script")
    if any(token in text for token in ["api", "integration", "webhook", "http"]):
        selected_keys.append("rest.call")

    if not selected_keys:
        selected_keys = ["rest.call"]

    selected = [item for item in catalog if item["key"] in selected_keys]
    return selected


def _slugify_name(value: str) -> str:
    raw = (value or "").strip().lower()
    chars = [ch if ch.isalnum() else "-" for ch in raw]
    slug = "".join(chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return slug[:64] or "bot"


def _build_conversational_manifest(bot_name: str, description: str, user_interests_goals: str, bot_type: str) -> Dict[str, Any]:
    return {
        "name": _slugify_name(bot_name),
        "version": "1.0.0",
        "language": "python",
        "description": description,
        "entrypoint": "src/agent.py",
        "timeout_seconds": 300,
        "schedule": {
            "type": "interval",
            "interval_seconds": 3600,
            "enabled": False,
        },
        "environment": {
            "BOT_NAME": bot_name,
            "BOT_TYPE": bot_type,
            "USER_GOALS": user_interests_goals,
        },
    }


def _generate_conversational_package_zip(name_slug: str, manifest: Dict[str, Any]) -> tuple:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    filename = f"{name_slug}-conversational-{timestamp}.zip"
    storage_filename = f"pkg_{filename}"
    package_path = os.path.join(ARCHIVES_DIR, storage_filename)

    agent_source = (
        "import json\n"
        "import os\n\n"
        "def main() -> None:\n"
        "    print(json.dumps({\n"
        "        'status': 'ok',\n"
        "        'bot_name': os.getenv('BOT_NAME', 'conversational-bot'),\n"
        "        'bot_type': os.getenv('BOT_TYPE', ''),\n"
        "    }))\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as temp_manifest:
        json.dump(manifest, temp_manifest, indent=2)
        temp_manifest_path = temp_manifest.name

    try:
        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(temp_manifest_path, arcname="manifest.json")
            archive.writestr("src/agent.py", agent_source)
            archive.writestr("requirements.txt", "# Standard library only\n")
    finally:
        if os.path.exists(temp_manifest_path):
            os.remove(temp_manifest_path)

    return filename, package_path


def _persist_bot_artifacts(package_id: int, bot_name: str, user_name: str, user_interests_goals: str, bot_type: str, tool_keys: List[str]) -> Dict[str, str]:
    """Persist bot.md and userprofile.md artifacts while DB remains source of record."""
    base_dir = os.path.join(STORAGE_DIR, "bots", str(package_id))
    os.makedirs(base_dir, exist_ok=True)

    bot_md_path = os.path.join(base_dir, "bot.md")
    userprofile_md_path = os.path.join(base_dir, "userprofile.md")

    tool_lines = "\n".join([f"- `{key}`" for key in tool_keys]) if tool_keys else "- `rest.call`"
    bot_md = (
        f"# {bot_name}\n\n"
        f"## Type\n{bot_type}\n\n"
        "## Runtime Model\nUnified Bot Runtime (package-backed)\n\n"
        "## Tool Bindings\n"
        f"{tool_lines}\n"
    )
    userprofile_md = (
        "# User Profile\n\n"
        f"- Name: {user_name}\n"
        f"- Interests/Goals: {user_interests_goals}\n"
    )

    with open(bot_md_path, "w", encoding="utf-8") as f:
        f.write(bot_md)
    with open(userprofile_md_path, "w", encoding="utf-8") as f:
        f.write(userprofile_md)

    return {"bot_md": bot_md_path, "userprofile_md": userprofile_md_path}
