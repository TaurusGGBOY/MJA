# AGENTS.md

This file contains the public development guidance for MJA contributors.

## Project scope

MJA is a MaaFramework-based automation project for the Android version of
《对决！剑之川》. The repository contains Python support code, Maa pipeline
resources, tests, and optional native build helpers.

## Development rules

- Keep runtime paths configurable and relative to the repository whenever
  possible. Do not commit machine-specific absolute paths, hostnames, IP
  addresses, account identifiers, credentials, or diagnostic dumps.
- Treat screenshots and OCR fixtures as potentially sensitive. Redact account
  names, user IDs, chat content, and other personal data before committing.
- Keep task state in the native MFW state model. Do not introduce a second
  business-result enum or result file.
- For pipeline changes, add or update focused tests and run the relevant test
  files before committing.
- Keep Android emulator settings explicit. The supported GPU backend is
  `host`; do not silently replace it with software or auto rendering.
- Do not add payment, login, verification-code, or credential automation.

## Local setup

See [README.md](README.md) for dependencies and the supported MFW/ADB entry
point. Put local SDKs, virtual environments, build outputs, and runtime logs
under ignored paths or outside the repository.

## Pull requests

Describe the user-visible behavior, tests run, fixture changes, and any
third-party assets or licenses involved. Never include private runtime logs or
unredacted game screenshots in a pull request.

## Branch workflow

- Work on short-lived `feat/*`, `fix/*`, `docs/*`, or `chore/*` branches.
- Merge into `main` through a squash pull request; do not push directly.
- GitHub Actions is disabled, so run focused tests locally before opening a PR.
