# Open-Source Release Checklist

Use this checklist before publishing CrucibleAgentPlatform to the broader community.

## 1. Licensing and repository settings

- Choose the public license you want to use for the release.
- Update the root LICENSE file if you want the repository to be truly open source.
- Confirm the README license section matches the actual license terms.
- Enable GitHub Issues and Discussions if you want community feedback.

## 2. Security and privacy review

- Confirm that `.env.sample` contains only placeholders and no live secrets.
- Verify that example manifests, scripts, and docs do not contain personal tokens, internal URLs, or customer-specific data.
- Review logs and screenshots for sensitive values before publishing them.
- Ensure the secret management flow is documented clearly for contributors.

## 3. Documentation quality

- Confirm the quick-start steps work on a clean machine.
- Make sure the README matches the current API routes and startup scripts.
- Keep example package instructions aligned with the watcher-based deployment flow.
- Add screenshots or a short demo if you want a stronger first-time contributor experience.

## 4. Project hygiene

- Run the relevant test suite before tagging a release.
- Remove dead links, placeholder repository URLs, and stale product names.
- Check package manifests and sample JSON files for validity.
- Review the repository for large generated files or local-only artifacts that should not be committed.

## 5. Community readiness

- Keep [CONTRIBUTING.md](../CONTRIBUTING.md) up to date.
- Consider adding a CODE_OF_CONDUCT and SECURITY policy for public collaboration.
- Document how maintainers prefer bugs, feature requests, and security reports to be submitted.
- Add release notes summarizing the first public version.

## Suggested pre-release commands

```bash
./scripts/start.sh --daemon
./scripts/run_tests.sh --api -q
curl http://localhost:8080/health
curl http://localhost:8080/mcp/health
```
