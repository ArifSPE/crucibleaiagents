---
applyTo: "{api,worker,scheduler,watchers,agents,skills,tools,shared}/**/*.{py,ts,js}"
---

# Backend Instructions

Apply these rules to backend and platform services.

## Service boundaries

- `api` handles request validation, auth, orchestration entrypoints, and response shaping.
- `worker` executes jobs, agent runs, tool calls, and skill calls.
- `scheduler` creates and dispatches time-based or recurring work.
- `watchers` monitor configured directories and publish normalized events.
- `agents` contains agent definitions, packaging helpers, manifests, and runtime adapters.
- `skills` contains reusable capability modules.
- `tools` contains externally or internally callable tool implementations.

Do not blur these responsibilities.

## Execution model

- Agent execution must be modeled as jobs or runs with explicit lifecycle states.
- Use clear state names such as:
  - pending
  - queued
  - running
  - succeeded
  - failed
  - cancelled
  - timed_out
- Persist or emit state transitions consistently.
- Capture start time, end time, duration, actor, and relevant identifiers.

## Contracts and interfaces

Prefer stable contracts for:
- agent manifest
- skill definition
- tool definition
- watcher event
- scheduler job
- run status
- audit event
- log record

Use typed models for all cross-component payloads.

Suggested model examples:
- AgentManifest
- AgentRunRequest
- AgentRunResult
- ToolInvocation
- ToolInvocationResult
- SkillDescriptor
- WatcherEvent
- ScheduledJob
- AuditEvent

## Logging and transparency

Use structured logs only.

Every major event should include:
- event_type
- timestamp
- component
- agent_id when applicable
- run_id when applicable
- request_id when applicable
- status
- duration_ms when applicable

Do not log full secret values, raw tokens, or sensitive file contents.

For tool and skill execution, log:
- name
- version if available
- invocation status
- safe input summary
- safe output summary
- retries
- exception class on failure

## Security

Assume all agent packages and runtime inputs are untrusted.

- Validate manifests before deployment.
- Validate file paths and prevent path traversal.
- Restrict filesystem access.
- Restrict network access by policy where supported.
- Enforce explicit permissions for tools and skills.
- Prefer signed or checksummed packages if packaging is implemented.
- Fail closed on invalid policy or missing configuration.
- Add audit logs for permission checks and denials.

## Scheduler rules

- Scheduler must create jobs, not execute heavy work inline.
- Long-running work must be delegated to workers.
- All schedules must be traceable to created jobs and resulting runs.
- Avoid duplicate execution; prefer idempotency keys or dedup safeguards.

## Watcher rules

- Watchers must normalize file system events into stable event payloads.
- Debounce noisy file changes when appropriate.
- Watchers should publish events or enqueue jobs rather than directly performing large workflows.
- Watchers must handle missing directories, permission errors, and restarts gracefully.

## Extensibility

When adding new skills or tools:
- register through a central registry
- expose metadata
- define input schema
- define output schema
- document permission requirements
- support versioning where practical

When adding deployment helpers:
- keep packaging, validation, storage, and execution concerns separate
- support both local and Docker workflows
- prefer convention over scattered manual steps

## Error handling

- Never swallow exceptions silently.
- Return structured error responses.
- Emit logs with clear failure reasons.
- Distinguish validation errors, policy errors, runtime errors, external dependency errors, and timeout errors.

## Testing expectations

Add tests for:
- manifest validation
- agent run state transitions
- permission enforcement
- scheduler dispatch logic
- watcher event normalization
- tool registry behavior
- skill loading behavior
- Docker/local configuration behavior where practical