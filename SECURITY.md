# Security Policy

## Supported Versions

The current development branch is the supported version.

## Reporting Vulnerabilities

Please report security issues privately to the project maintainer before publishing details. If the project is hosted on GitHub, use GitHub Security Advisories when available.

Include:

- Affected version or commit.
- Reproduction steps.
- Impact assessment.
- Whether the issue can trigger local command execution, shell execution, credential exposure, or task approval bypass.

## Security Boundaries

- MyAgentWatch is intended for local or trusted network deployment.
- Approval only authorizes the server-side task lifecycle. The local daemon policy remains the final execution gate.
- Shell tasks must pass `daemon_policy.json` and `shell_allowlist`.
- Do not commit `.env`, `config.json`, tokens, private keys, local databases, logs, or daemon data.

