# Contributing to CrucibleAgentPlatform

Thank you for contributing.

This project prioritizes security, transparency, maintainability, extensibility, and operational simplicity. Please follow the guidelines below for code changes, pull requests, and reviews.

## Getting Started

1. Fork the repository.
2. Clone your fork.
3. Create and activate a virtual environment.
4. Install dependencies.
5. Run tests before opening a PR.

```bash
git clone <your-fork-url>
cd crucibleaiagents
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/run_tests.sh --api -q
```

## Development Principles

- Keep separation of concerns between API, worker, scheduler, watcher, frontend, and shared modules.
- Keep business logic in service layers, not HTTP route handlers.
- Treat all external input as untrusted.
- Never hardcode secrets or credentials.
- Prefer structured logging over print statements.
- Keep functions small and composable.
- Add or update tests for all behavior changes.
- Update documentation when behavior changes.

## Coding Guidelines

### Python

- Follow PEP 8.
- Use type hints for all new/updated functions.
- Add concise docstrings where behavior is not obvious.
- Use explicit error handling and consistent API responses.
- Prefer dependency injection patterns for services and integrations.

### FastAPI

- Keep routers thin.
- Put CRUD and business rules in `api/services`.
- Validate request models in schemas and keep responses predictable.

### Frontend

- Use React functional components and hooks.
- Keep API logic separate from UI components.
- Include explicit loading, error, and empty states.

## Branch Naming

Use descriptive branch names:

- `feature/<short-description>`
- `fix/<short-description>`
- `refactor/<short-description>`
- `docs/<short-description>`
- `test/<short-description>`

Examples:

- `feature/add-secret-rotation-endpoint`
- `fix/daemon-health-check-timeout`
- `docs/update-watcher-deployment-guide`

## Commit Message Guidelines

Use clear, focused commits in imperative mood.

Format:

`<type>: <short summary>`

Recommended types:

- `feat`
- `fix`
- `refactor`
- `test`
- `docs`
- `chore`

Examples:

- `feat: add schedule activation endpoint`
- `fix: handle missing manifest fields in package parser`
- `test: cover llm provider credential serialization`

## Pull Request Guidelines

Each PR should be scoped, reviewable, and traceable.

### PR Title

Use the same style as commits:

`<type>: <short summary>`

### PR Description Checklist

Include:

1. What changed.
2. Why it changed.
3. Any risks or breaking changes.
4. Test evidence (commands and results).
5. Related issue(s), if applicable.

GitHub uses the default PR template at `.github/pull_request_template.md`.

Suggested template:

```markdown
## Summary
- ...

## Why
- ...

## Changes
- ...

## Test Evidence
- `./scripts/run_tests.sh --api -q`
- Result: all tests passed

## Risks / Rollback
- ...
```

### Before Requesting Review

- Rebase on latest main branch.
- Run relevant tests locally.
- Ensure no secrets were added to code, tests, logs, or docs.
- Ensure docs are updated for behavior/config/API changes.
- Keep PR size manageable.

## Testing Expectations

At minimum, run tests impacted by your changes.

Common commands:

```bash
./scripts/run_tests.sh --api -q
./scripts/run_tests.sh --all
./scripts/run_tests.sh --file api/tests/test_runs.py
```

For bug fixes:

- Add a regression test that fails before and passes after your change.

## Security and Compliance Requirements

- Do not commit secrets, keys, tokens, certificates, or credential material.
- Use environment variables or approved secret providers.
- Log security-relevant lifecycle events, but never log secret values.
- Validate and sanitize all inputs.
- Prefer allowlists for permissions and access constraints.

## Documentation Expectations

Update docs when you change:

- API behavior or schema
- environment variables
- deployment flow
- operational scripts
- security-sensitive behavior

## Review and Merge

- Address review feedback with follow-up commits.
- Keep discussion resolved before merge.
- Prefer squash merge for small PRs; use merge commits only when preserving history is important.

## Need Help?

For questions, open an issue or use the project support channels listed in the README.
