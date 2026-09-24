# AGENTS.md

## Workflow

- Work on `main`; create or switch branches/worktrees only when explicitly requested.
- Run focused tests locally before committing; GitHub Actions is disabled.
- Add or update focused tests for pipeline changes.
- PRs must describe behavior changes, tests run, fixture updates, and third-party assets/licenses.

## Development rules

- Use only native MFW task states; no parallel business-result enum or result file.
- Configure emulator settings explicitly with GPU `host`; never substitute software or auto rendering.
- Do not automate payments, login, verification codes, or credentials.
- Keep runtime paths configurable and repository-relative where possible.
- Keep local SDKs, virtual environments, build outputs, and runtime logs ignored or outside the repository.
- Exclude machine-specific paths/hostnames/IPs, account identifiers, credentials, and diagnostic dumps from commits and PRs.
- Redact personal data (account names, user IDs, chat) from screenshots and OCR fixtures before committing or sharing in PRs.

## References

- [README.md](README.md): setup and MFW/ADB entry points.
- [CONTRIBUTING.md](CONTRIBUTING.md): contribution workflow and checks.
- [SECURITY.md](SECURITY.md): handling sensitive data and reports.
- [Native task status](docs/adr/0001-use-mfw-native-task-status.md): MFW state semantics.
