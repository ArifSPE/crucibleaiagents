import json
import os
import pathlib
import subprocess
import sys

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
_log = logging.getLogger("runner.system")


def read_manifest(code_dir: str):
    manifest_path = os.path.join(code_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        _log.error("manifest.json not found in package directory")
        return None

    with open(manifest_path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            _log.error("Invalid JSON in manifest.json")
            return None


def detect_package_root(code_dir: str) -> pathlib.Path:
    base_dir = pathlib.Path(code_dir).resolve()
    root_manifest = base_dir / "manifest.json"
    if root_manifest.is_file():
        return base_dir

    manifest_candidates = [
        path for path in base_dir.rglob("manifest.json")
        if path.is_file() and "." not in path.relative_to(base_dir).parts[0]
    ]
    if not manifest_candidates:
        return base_dir

    manifest_candidates.sort(key=lambda path: (len(path.relative_to(base_dir).parts), str(path)))
    return manifest_candidates[0].parent


def normalize_language(language: str) -> str:
    normalized = (language or "python").strip().lower()
    language_map = {
        "python": "python",
        "py": "python",
        "node": "node.js",
        "nodejs": "node.js",
        "node.js": "node.js",
        "javascript": "node.js",
        "js": "node.js",
        "typescript": "typescript",
        "ts": "typescript",
    }
    return language_map.get(normalized, normalized)


def resolve_entrypoint(code_dir: str, entrypoint: str, language: str) -> pathlib.Path:
    base_dir = pathlib.Path(code_dir).resolve()
    requested_path = pathlib.Path(entrypoint)

    if requested_path.is_absolute():
        raise ValueError("Entrypoint must be a relative path inside the package")

    resolved_path = (base_dir / requested_path).resolve()
    try:
        resolved_path.relative_to(base_dir)
    except ValueError as exc:
        raise ValueError("Entrypoint escapes package directory") from exc

    expected_suffix_by_language = {
        "python": ".py",
        "node.js": ".js",
        "typescript": ".ts",
    }
    expected_suffix = expected_suffix_by_language.get(language)
    if not expected_suffix:
        raise ValueError(f"Unsupported agent language '{language}'")

    if resolved_path.suffix != expected_suffix:
        raise ValueError(f"Entrypoint must be a {expected_suffix} file for {language}")

    if not resolved_path.is_file():
        raise ValueError(f"Entrypoint {entrypoint} not found in package")

    return resolved_path


def build_agent_base_environment(process_env: dict) -> dict:
    blocked_keys = {
        "AGENTFLOW_API_TOKEN",
        "AGENTFLOW_SECRETS_ADMIN_TOKEN",
        "SECRETS_ENCRYPTION_KEY",
    }
    return {k: v for k, v in process_env.items() if k not in blocked_keys}


def main():
    pkg_dir_path = os.environ.get("PACKAGE_DIR")
    if not pkg_dir_path:
        _log.error("PACKAGE_DIR environment variable is required")
        sys.exit(1)

    if not os.path.isdir(pkg_dir_path):
        _log.error(f"Package directory not found or invalid: {pkg_dir_path}")
        sys.exit(1)

    package_root = detect_package_root(pkg_dir_path)
    manifest = read_manifest(str(package_root)) or {}

    language = normalize_language(manifest.get("language") or "python")
    default_entrypoint = {
        "python": "src/agent.py",
        "node.js": "src/agent.js",
        "typescript": "src/agent.ts",
    }.get(language, "src/agent.py")

    entrypoint = manifest.get("entrypoint") or default_entrypoint
    try:
        entry_path = resolve_entrypoint(str(package_root), entrypoint, language)
    except ValueError as exc:
        _log.error(str(exc))
        sys.exit(2)

    # Runtime dependency installation (best effort, consistent with legacy runner behavior).
    if language == "python":
        requirements = package_root / "requirements.txt"
        if requirements.exists():
            rc = subprocess.call([sys.executable, "-m", "pip", "install", "--no-warn-script-location", "-r", str(requirements)])
            if rc != 0:
                _log.error("Failed to install Python dependencies")
                sys.exit(3)
    elif language in ("node.js", "typescript"):
        package_json = package_root / "package.json"
        if package_json.exists():
            rc = subprocess.call(["npm", "install", "--omit=dev"], cwd=str(package_root))
            if rc != 0:
                _log.error("Failed to install Node/TypeScript dependencies")
                sys.exit(3)

    env = build_agent_base_environment(os.environ.copy())
    manifest_env = manifest.get("environment") or {}
    if isinstance(manifest_env, dict):
        for k, v in manifest_env.items():
            env[str(k)] = str(v)

    if language == "python":
        cmd = [sys.executable, str(entry_path)]
    elif language == "node.js":
        cmd = ["node", str(entry_path)]
    else:
        cmd = ["npx", "--yes", "tsx", str(entry_path)]

    rc = subprocess.call(cmd, cwd=str(package_root), env=env)
    sys.exit(rc)


if __name__ == "__main__":
    main()
