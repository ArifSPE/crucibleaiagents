---
applyTo: "frontend/**/*.{js,jsx,ts,tsx}"
---

# Frontend Instructions

This frontend is a React.js control plane for a secure agent deployment platform.

## UI goals

Optimize for:
- operational clarity
- transparency
- security visibility
- simple deployment flows
- easy troubleshooting
- future growth in tools, skills, and agent types

## Required frontend areas

Prefer UI patterns that support:
- agent catalog
- agent deployment
- agent run history
- run details
- live or near-real-time logs
- tool and skill registry views
- scheduler management
- directory watcher status and events
- environment/configuration visibility
- health/status dashboards
- audit trail exploration

## Component rules

- Use React functional components only.
- Use hooks.
- Keep components small and focused.
- Separate page components from reusable UI components.
- Separate data-fetching logic from presentational logic where practical.
- Avoid very large all-in-one components.

Suggested structure:
- pages/
- components/
- hooks/
- services/
- types/
- utils/

## UX rules

- Always show loading states.
- Always show clear empty states.
- Always show actionable error states.
- Use confirmations for destructive actions.
- Make run status and audit status easy to scan.
- Prefer timeline and event-table views for logs and audit trails.
- Surface correlation identifiers such as run_id and job_id where useful.

## Transparency rules

The frontend should make system behavior understandable.

- Show agent lifecycle clearly.
- Show which skills and tools were used during a run.
- Show run timestamps and durations.
- Show summarized inputs and outputs when safe.
- Show permission denials and policy errors clearly.
- Do not expose secrets, tokens, or unsafe raw payloads in the UI.

## API integration rules

- Keep API calls in service modules.
- Use typed request and response models.
- Normalize backend errors for consistent display.
- Handle polling or streaming carefully for log views.
- Prefer reusable hooks for common data access patterns.

## Security rules

- Never hardcode secrets in frontend code.
- Do not trust client-side validation alone.
- Avoid rendering sensitive raw data directly.
- Sanitize or escape unsafe content before rendering.

## Design guidance

The UI should feel like an operator console.

Prefer interfaces such as:
- deployment wizard
- run detail drawer or detail page
- log console with filters
- audit timeline
- scheduler table
- watcher event feed
- tools and skills registry table with metadata

## Future-proofing

The platform will add more tools, skills, and easier build/deploy flows.

Design components so they can expand to support:
- agent templates
- one-click deployment
- package validation feedback
- versioned skills and tools
- side-by-side run comparison
- multi-environment deployment in the future

## Testing expectations

Add tests for:
- page rendering
- empty/loading/error states
- log filtering
- run status display
- deployment form validation
- scheduler and watcher views