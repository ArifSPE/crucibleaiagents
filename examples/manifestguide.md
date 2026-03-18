# Manifest Guide (Examples Reference)

This guide summarizes how `manifest.json` is used across the `examples/` packages in this repository.

It is based on:
- Current example manifests in `examples/*/manifest.json`
- The schema in `schemas/bot-manifest.schema.json`

## 1) Minimal Valid Manifest

According to the schema, these fields are required:
- `name`
- `version` (semver, for example `1.0.0`)
- `language` (`python`, `typescript`, or `node.js`)
- `entrypoint`

Minimal example:

```json
{
  "name": "my-agent",
  "version": "1.0.0",
  "language": "python",
  "entrypoint": "src/agent.py"
}
```

## 2) Common Fields (Used In This Repo)

### Core runtime fields
- `description`: Human-readable summary.
- `timeout_seconds`: Agent timeout in seconds.

Notes:
- Schema range is `10` to `3600`.
- Some daemon examples use `0` to indicate long-running behavior. Keep this consistent with your runtime mode expectations.

### Environment and secrets
- `environment`: Key-value environment variables.

Patterns used in examples:
- Plain values: `"LOG_LEVEL": "INFO"`
- Secret placeholders: `"TAVILY_API_KEY": "{secrets.TAVILY_API_KEY}"`

Recommendation:
- Keep secrets out of plain text values.
- Use placeholders and platform secret injection.

### Scheduling
Most examples use a nested `schedule` object:

```json
"schedule": {
  "type": "interval",
  "interval_seconds": 300,
  "enabled": true
}
```

Observed variants:
- Interval schedules: `type: interval` + `interval_seconds`
- Cron schedules: `type: cron` with a cron field

Schema-defined schedule keys:
- `enabled`
- `type` (`interval`, `cron`, `at`)
- `interval_seconds`
- `cron_expr`
- `timestamp`

Important:
- Some examples use `cron_expression` instead of `cron_expr`.
- One example uses top-level `schedule_enabled` and `schedule_cron`.
- Because `additionalProperties` is true, these may parse, but for consistency prefer schema-aligned keys under `schedule`.

### LLM provider configuration
Used by LLM-enabled examples:

```json
"llm_provider": {
  "use_platform": true,
  "provider_id": 4
}
```

Also seen:
- `use_platform: false` for direct endpoint configuration via environment.
- Additional informational fields such as `note`.

### Tool bindings
Used in package/tool demo flows:

```json
"tool_bindings": [
  { "tool_key": "shell.command", "config": { "default_command": "date" } },
  { "tool_key": "rest.call", "config": { "default_url": "https://api.github.com" } }
]
```

Schema-allowed tool keys:
- `shell.command`
- `shell.script`
- `rest.call`

### Daemon-specific fields
Used in daemon examples:
- `runtime_mode`: typically `daemon`
- `auto_start`: boolean
- `health_check`: object (`type`, `path`, `port`, intervals/timeouts)
- `restart_policy`: for example `on-failure`
- `expose`: host exposure metadata (for example HTTP port/path)

### Other optional metadata seen in examples
- `agent_id`
- `tags`
- `secrets` (list of expected secret names)
- `dependencies`
- `action`
- `configuration`, `features`, `system_prompt`, `error_handling`, `observability`

These are currently tolerated by schema (`additionalProperties: true`).

## 3) Recommended Baseline Template

Use this template for new examples unless you need daemon or advanced behavior:

```json
{
  "name": "my-agent",
  "version": "1.0.0",
  "language": "python",
  "description": "Short summary of what this agent does",
  "entrypoint": "src/agent.py",
  "timeout_seconds": 120,
  "environment": {
    "MY_CONFIG": "value",
    "API_KEY": "{secrets.API_KEY}"
  },
  "schedule": {
    "type": "interval",
    "interval_seconds": 300,
    "enabled": false
  }
}
```

## 4) Common Pitfalls Seen In Current Examples

- Duplicate JSON key in one file (`webhooks` appears twice in one manifest). JSON parsers typically keep only the last key.
- Mixed cron field naming (`cron_expr` vs `cron_expression` vs top-level `schedule_cron`).
- Inconsistent `action` values (`new`, `Update`) and casing.
- Very large manifest metadata blocks can reduce readability for operational use.

## 5) Example Manifests In This Repo

- [daemon-agent](daemon-agent/manifest.json)
- [fastapi-daemon-agent](fastapi-daemon-agent/manifest.json)
- [fresh-test-package](fresh-test-package/manifest.json)
- [local-automation-bot](local-automation-bot/manifest.json)
- [msteam-channel-summarizer](msteam-channel-summarizer/manifest.json)
- [platform-llm-agent](platform-llm-agent/manifest.json)
- [react-ollama-agent](react-ollama-agent/manifest.json)
- [sample-bot-package](sample-bot-package/manifest.json)
- [samplepackage](samplepackage/manifest.json)
- [scheduled-package](scheduled-package/manifest.json)
- [sleep-test-agent](sleep-test-agent/manifest.json)
- [tools-demo-agent](tools-demo-agent/manifest.json)
- [ts-sample-agent](ts-sample-agent/manifest.json)

## 6) Validation Tips

Quick checks before packaging:
- Ensure valid JSON (no duplicate keys, no trailing commas).
- Ensure required fields exist and `version` is semver.
- Ensure `entrypoint` exists in the package.
- Keep schedule keys schema-aligned under `schedule` when possible.
- Keep secrets in placeholders, not plaintext.
