"""Local automation bot with safety guardrails.

Modes:
- file_organize: Move files in TARGET_DIR into type-based folders.
- email_cleanup: Run IMAP cleanup action based on EMAIL_CLEANUP_QUERY.
- both: Execute file_organize then email_cleanup.

Security defaults:
- ENABLE_LOCAL_AUTOMATION must be explicitly set to true.
- AUTOMATION_DRY_RUN defaults to true.
- TARGET_DIR must be inside ALLOWLIST_ROOTS.
"""

from __future__ import annotations

import imaplib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


FILE_BUCKETS: Dict[str, str] = {
    ".jpg": "images",
    ".jpeg": "images",
    ".png": "images",
    ".gif": "images",
    ".svg": "images",
    ".pdf": "documents",
    ".doc": "documents",
    ".docx": "documents",
    ".txt": "documents",
    ".csv": "documents",
    ".xlsx": "documents",
    ".zip": "archives",
    ".tar": "archives",
    ".gz": "archives",
    ".mp4": "videos",
    ".mov": "videos",
    ".mp3": "audio",
    ".wav": "audio",
}


@dataclass
class Config:
    enabled: bool
    mode: str
    dry_run: bool
    allowlist_roots: List[Path]
    target_dir: Path
    file_action: str
    imap_host: str
    imap_port: int
    imap_username: str
    imap_password: str
    email_action: str
    email_move_folder: str
    email_query: str
    email_max_messages: int


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _as_bool(value: str, default: bool = False) -> bool:
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _load_config() -> Config:
    roots_raw = _env("ALLOWLIST_ROOTS", "")
    root_candidates = [item.strip() for item in roots_raw.split(",") if item.strip()]
    allowlist = [Path(item).expanduser().resolve() for item in root_candidates]

    target_dir_raw = _env("TARGET_DIR", "")
    target_dir = Path(target_dir_raw).expanduser().resolve() if target_dir_raw else Path.cwd().resolve()

    return Config(
        enabled=_as_bool(_env("ENABLE_LOCAL_AUTOMATION", "false")),
        mode=_env("AUTOMATION_MODE", "file_organize").lower(),
        dry_run=_as_bool(_env("AUTOMATION_DRY_RUN", "true"), default=True),
        allowlist_roots=allowlist,
        target_dir=target_dir,
        file_action=_env("FILE_ACTION", "move").lower(),
        imap_host=_env("IMAP_HOST", ""),
        imap_port=int(_env("IMAP_PORT", "993") or "993"),
        imap_username=_env("IMAP_USERNAME", ""),
        imap_password=_env("IMAP_PASSWORD", ""),
        email_action=_env("EMAIL_ACTION", "move").lower(),
        email_move_folder=_env("EMAIL_MOVE_FOLDER", "Archive"),
        email_query=_env("EMAIL_CLEANUP_QUERY", "(SEEN BEFORE 01-Jan-2024)"),
        email_max_messages=int(_env("EMAIL_MAX_MESSAGES", "50") or "50"),
    )


def _is_under_allowlist(path: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _validate_guardrails(cfg: Config) -> None:
    if not cfg.enabled:
        raise RuntimeError("ENABLE_LOCAL_AUTOMATION is false. Refusing to run local automation tasks.")

    if not cfg.allowlist_roots:
        raise RuntimeError("ALLOWLIST_ROOTS is empty. Set one or more absolute paths via secrets.")

    if not _is_under_allowlist(cfg.target_dir, cfg.allowlist_roots):
        raise RuntimeError(
            f"TARGET_DIR {cfg.target_dir} is not inside ALLOWLIST_ROOTS: {', '.join(map(str, cfg.allowlist_roots))}"
        )


def _bucket_for_file(path: Path) -> str:
    return FILE_BUCKETS.get(path.suffix.lower(), "other")


def run_file_organize(cfg: Config) -> Tuple[int, int]:
    if not cfg.target_dir.exists() or not cfg.target_dir.is_dir():
        raise RuntimeError(f"TARGET_DIR not found or not a directory: {cfg.target_dir}")

    moved = 0
    skipped = 0

    for item in cfg.target_dir.iterdir():
        if item.is_dir():
            skipped += 1
            continue

        bucket = _bucket_for_file(item)
        destination_dir = cfg.target_dir / bucket
        destination = destination_dir / item.name

        if cfg.file_action not in {"move", "copy"}:
            raise RuntimeError(f"Unsupported FILE_ACTION: {cfg.file_action}")

        if cfg.dry_run:
            print(f"[DRY-RUN] {cfg.file_action} {item} -> {destination}")
            moved += 1
            continue

        destination_dir.mkdir(parents=True, exist_ok=True)
        if cfg.file_action == "move":
            shutil.move(str(item), str(destination))
        else:
            shutil.copy2(str(item), str(destination))
        moved += 1

    return moved, skipped


def _imap_login(cfg: Config) -> imaplib.IMAP4_SSL:
    if not (cfg.imap_host and cfg.imap_username and cfg.imap_password):
        raise RuntimeError("IMAP credentials are incomplete. Set IMAP_HOST/IMAP_USERNAME/IMAP_PASSWORD secrets.")

    client = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
    client.login(cfg.imap_username, cfg.imap_password)
    return client


def run_email_cleanup(cfg: Config) -> int:
    if cfg.email_action not in {"move", "delete", "mark_read"}:
        raise RuntimeError("EMAIL_ACTION must be one of: move, delete, mark_read")

    client = _imap_login(cfg)
    try:
        status, _ = client.select("INBOX")
        if status != "OK":
            raise RuntimeError("Could not select INBOX")

        status, data = client.search(None, cfg.email_query)
        if status != "OK":
            raise RuntimeError(f"IMAP search failed for query: {cfg.email_query}")

        ids = data[0].split() if data and data[0] else []
        ids = ids[: cfg.email_max_messages]

        if not ids:
            print("No emails matched cleanup query.")
            return 0

        print(f"Matched {len(ids)} email(s) for cleanup action={cfg.email_action} (dry_run={cfg.dry_run})")

        for msg_id in ids:
            msg_text = msg_id.decode("utf-8", errors="ignore")
            if cfg.dry_run:
                print(f"[DRY-RUN] email {msg_text}: action={cfg.email_action}")
                continue

            if cfg.email_action == "mark_read":
                client.store(msg_id, "+FLAGS", r"(\\Seen)")
            elif cfg.email_action == "move":
                client.copy(msg_id, cfg.email_move_folder)
                client.store(msg_id, "+FLAGS", r"(\\Deleted)")
            elif cfg.email_action == "delete":
                client.store(msg_id, "+FLAGS", r"(\\Deleted)")

        if not cfg.dry_run and cfg.email_action in {"move", "delete"}:
            client.expunge()

        return len(ids)
    finally:
        try:
            client.close()
        except Exception:
            pass
        client.logout()


def main() -> None:
    cfg = _load_config()
    _validate_guardrails(cfg)

    print(f"Automation mode={cfg.mode}, dry_run={cfg.dry_run}, target={cfg.target_dir}")

    if cfg.mode in {"file_organize", "both"}:
        moved, skipped = run_file_organize(cfg)
        print(f"File organize complete. processed={moved}, skipped={skipped}")

    if cfg.mode in {"email_cleanup", "both"}:
        affected = run_email_cleanup(cfg)
        print(f"Email cleanup complete. affected={affected}")

    if cfg.mode not in {"file_organize", "email_cleanup", "both"}:
        raise RuntimeError("AUTOMATION_MODE must be one of: file_organize, email_cleanup, both")


if __name__ == "__main__":
    main()
