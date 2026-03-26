## Summary
- Describe the main change(s).
- Keep this concise and clear.

## Why
- Explain the problem or motivation.
- Link requirement, bug, or design context.

## Changes
- List key implementation details.
- Mention impacted modules and any contract changes.

## Test Evidence
- Include the exact commands you ran.
- Include the result summary.

Example:
- ./scripts/run_tests.sh --api -q
- Result: all tests passed

## Risks / Rollback
- Note behavior risks, migration concerns, or edge cases.
- Describe rollback approach if needed.

## Security Review
- [ ] No secrets, tokens, keys, or credentials were added.
- [ ] Inputs are validated and untrusted data is handled safely.
- [ ] Security-relevant events are logged without exposing sensitive values.

## Documentation
- [ ] README/docs updated for behavior or configuration changes.
- [ ] API/schema changes documented.
- [ ] Operational changes documented (scripts, env vars, deployment flow).

## Contributor Checklist
- [ ] Branch is up to date with main.
- [ ] Code follows project coding standards.
- [ ] Tests added or updated for new behavior.
- [ ] PR is scoped and ready for review.
- [ ] Related issue linked (if applicable).
