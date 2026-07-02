# MyAgentWatch

MyAgentWatch is a local-first multi-agent observability and collaboration dashboard. It provides agent status monitoring, chat, structured agent inbox, task cards, task approval, and a daemon-facing execution queue.

Copyright (C) 2026 Tianyu.

This project is designed and maintained by Tianyu. Parts of the implementation were generated with AI assistance and reviewed, edited, and integrated into this project.

## Current Focus

- Web chat is the primary human entry point.
- `@Agent`, private messages, `/assign`, `/code`, and `/shell` can create structured `agent_tasks`.
- High-risk task types require approval before the daemon can claim them.
- `myagentwatch-cli` is the agent-side client and daemon runner.

## Run Locally

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

Default URL:

```text
http://127.0.0.1:10000/
```

## CLI Connection

Install or run `myagentwatch-cli`, then connect it to the local server:

```powershell
myaw connect http://127.0.0.1:10000/
myaw status
myaw conversations
myaw tasks list
```

## Safety Model

- Normal group chat only writes chat history.
- `@codex` and private agent messages create `reply` tasks.
- `/assign`, `/code`, and `/shell` create higher-risk execution tasks.
- `reply` tasks are normally `not_required`; `code_change`, `shell_command`, and `custom` tasks default to `pending`.
- Rejected or pending tasks are not claimable by the daemon.
- Server approval does not bypass local daemon policy or shell allowlists.

## Tests

```powershell
python tests\test_smoke.py
python -m py_compile app.py myagentwatch\db.py myagentwatch\agent_tasks.py routes\agent_tasks_api.py
node --check static\js\chat-wechat.js
```

## License

MyAgentWatch is licensed under `AGPL-3.0-only`. See [LICENSE](LICENSE).

