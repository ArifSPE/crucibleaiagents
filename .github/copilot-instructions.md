# Copilot Instructions

This repository contains a secure agent deployment and execution platform.

The platform supports:
- agent packaging, deployment, and execution
- secure tool and skill invocation
- per-agent logging and audit trails for transparency
- API, worker, scheduler, and directory watcher components
- local development mode and Docker Compose deployment
- extensible skills, tools, and agent templates
- React.js frontend for management and observability

## Primary goals

When generating code for this repository, optimize for:
1. security
2. transparency
3. maintainability
4. extensibility
5. operational simplicity
6. safe local and containerized execution

## Core architectural rules

- Keep clear separation between:
  - api
  - worker
  - scheduler
  - watchers
  - frontend
  - shared libraries
- Business logic must not live in HTTP route handlers.
- Agent execution logic must not be coupled directly to UI logic.
- Scheduling logic must be isolated from execution logic.
- Directory watchers must emit structured events and must not directly contain business workflows.
- Skills and tools must be pluggable and registered through a stable interface.
- New components must be added in an extension-friendly way without changing core contracts unnecessarily.

## Security rules

Security is mandatory.

- Never hardcode secrets, API keys, tokens, credentials, or certificates.
- Read all secrets from environment variables or approved secret providers.
- Validate all external inputs.
- Treat agent code, uploaded bundles, and tool parameters as untrusted.
- Prefer allowlists over denylists for tool access, file access, network access, and execution permissions.
- Agent execution must be sandbox-aware and policy-driven.
- Log security-relevant events such as:
  - deployment
  - execution start and stop
  - tool calls
  - skill calls
  - file access events
  - scheduler triggers
  - watcher events
  - permission denials
  - failures and retries
- Never log secrets or raw credentials.
- Do not disable authentication, authorization, audit logging, or validation unless explicitly instructed.

## Transparency and auditability rules

This platform must provide strong observability.

- All major actions must emit structured logs.
- Logs must include correlation identifiers such as:
  - request_id
  - job_id
  - agent_id
  - run_id
  - tenant_id if multi-tenant support is added
- Every agent run should be traceable end to end.
- Tool calls and skill calls should record:
  - actor
  - input summary
  - output summary
  - duration
  - status
  - failure reason when applicable
- Prefer append-only audit records for critical lifecycle events.
- Use human-readable status values and stable machine-readable event types.

## Backend coding standards

- Prefer Python with type hints if writing backend code unless the existing module uses another language.
- Use small, composable functions.
- Use dependency injection where appropriate.
- Use structured logging instead of print statements.
- Use explicit interfaces or abstract base classes for tool, skill, watcher, scheduler, and agent runner contracts.
- Prefer async I/O for network-bound or I/O-heavy operations.
- Return structured error objects and consistent API response models.
- Avoid large monolithic classes.

## Frontend coding standards

- Use React functional components.
- Prefer hooks.
- Keep UI components focused and composable.
- Separate API client logic from presentation components.
- Build operator-focused screens for:
  - agent deployment
  - agent runs
  - logs
  - schedules
  - watcher events
  - tools
  - skills
  - configuration
- Prefer explicit loading, error, and empty states.

## Extensibility rules

This platform will evolve to support more skills, tools, and easier agent deployment.

- New tools and skills must implement stable registration interfaces.
- Avoid hardcoding tool lists or skill lists in multiple places.
- Prefer registry-based patterns.
- Agent templates should be reusable and versioned.
- Docker and local mode should behave consistently where possible.
- New deployment flows should minimize manual steps.

## Local and Docker rules

- Code must work in both local mode and Docker Compose unless explicitly documented otherwise.
- Avoid path assumptions that only work inside containers.
- Use environment-driven configuration.
- Health checks and startup dependencies should be considered for distributed components.
- Prefer deterministic startup and graceful shutdown handling.

## Testing rules

- Add tests for all new behavior.
- Test API validation and error handling.
- Test worker execution paths.
- Test scheduler trigger behavior.
- Test watcher event handling.
- Test access control and security boundaries where practical.
- Prefer unit tests first, integration tests for cross-component behavior.
- Mock external systems explicitly.

## Documentation rules

When generating new modules, also add or update:
- docstrings
- README sections if behavior changes materially
- sample configuration when needed
- architecture notes if a new subsystem is introduced

## What Copilot should optimize for

When proposing implementations, prefer:
- secure defaults
- simple deployment
- strong logging
- stable contracts
- clear separation of concerns
- future support for more tools, skills, and agent packaging workflows

Avoid:
- hidden side effects
- silent failures
- weak logging
- tightly coupled modules
- direct frontend-to-worker shortcuts
- introducing new frameworks without explicit instruction
- Hardcoding in the code