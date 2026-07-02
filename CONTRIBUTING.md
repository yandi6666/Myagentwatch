# Contributing

Thank you for helping improve MyAgentWatch.

## Issues

When opening an issue, include:

- What you expected to happen.
- What actually happened.
- Steps to reproduce.
- Relevant logs with secrets removed.
- Your OS, Python version, and whether `myagentwatch-cli` daemon was running.

## Pull Requests

- Keep changes focused.
- Preserve existing CLI and HTTP API compatibility unless the PR is explicitly a breaking change.
- Do not commit local databases, logs, tokens, daemon data, or private config files.
- Add or update tests for task queue, chat, inbox, daemon, and permission behavior.
- Document user-visible CLI or web changes.

## Local Checks

```powershell
python tests\test_smoke.py
python -m py_compile app.py myagentwatch\db.py myagentwatch\agent_tasks.py routes\agent_tasks_api.py
node --check static\js\chat-wechat.js
```

## Code Style

- Prefer small, explicit functions.
- Keep server-side task lifecycle changes auditable through `agent_task_events`.
- Avoid hidden telemetry, remote callbacks, or background execution that is not visible in local policy.

