# Local Automation Bot

A safe local automation bot package for local tasks, designed for AgentFlow local worker mode.

## Capabilities

- `file_organize`: Organize files in a target directory by extension buckets.
- `email_cleanup`: Run IMAP mailbox cleanup based on a query.
- `both`: Execute file organization and email cleanup in sequence.

## Safety Guardrails

- Requires `ENABLE_LOCAL_AUTOMATION=true` to run.
- Requires `ALLOWLIST_ROOTS` (absolute paths) and enforces `TARGET_DIR` under allowlist.
- Defaults to `AUTOMATION_DRY_RUN=true`.
- Supports non-destructive dry-run for both file and email tasks.

## Environment Variables

Core:
- `ENABLE_LOCAL_AUTOMATION`: `true|false`
- `AUTOMATION_MODE`: `file_organize|email_cleanup|both`
- `AUTOMATION_DRY_RUN`: `true|false`
- `ALLOWLIST_ROOTS`: comma-separated absolute roots, e.g. `/Users/arifshaikh/Downloads,/Users/arifshaikh/Documents`
- `TARGET_DIR`: absolute path under allowlist roots

File organization:
- `FILE_ACTION`: `move|copy` (default `move`)

Email cleanup:
- `IMAP_HOST`, `IMAP_PORT`, `IMAP_USERNAME`, `IMAP_PASSWORD`
- `EMAIL_CLEANUP_QUERY`: IMAP search query, e.g. `(SEEN BEFORE 01-Jan-2024)`
- `EMAIL_ACTION`: `move|delete|mark_read`
- `EMAIL_MOVE_FOLDER`: destination folder for move action
- `EMAIL_MAX_MESSAGES`: cap processed messages per run

## Usage in AgentFlow

1. Zip this folder and upload it as a package.
2. Set package secrets for:
   - `ALLOWLIST_ROOTS`
   - `TARGET_DIR`
   - optionally IMAP secrets (`IMAP_HOST`, `IMAP_USERNAME`, `IMAP_PASSWORD`)
3. Start with `AUTOMATION_DRY_RUN=true`.
4. Run package and inspect logs/events.
5. Flip `AUTOMATION_DRY_RUN=false` only after validating output.

## Important Note

For real local file operations, use `startup/start-all.sh` local mode (worker-local). In fully Dockerized worker mode, host file access is constrained by container mounts.
