# Release Checklist

Before publishing to GitHub:

- `LICENSE` exists and declares `AGPL-3.0-only`.
- `README.md`, `CONTRIBUTING.md`, and `SECURITY.md` exist.
- No secrets, tokens, private keys, `.env`, `config.json`, local databases, logs, or daemon data are committed.
- No private local paths are required for normal installation or runtime.
- `python tests\test_smoke.py` passes.
- Server `py_compile` passes.
- Frontend `node --check static\js\chat-wechat.js` passes.
- The daemon policy still blocks unapproved tasks and non-allowlisted shell commands.
- GitHub release notes mention the AI-assisted implementation note from `README.md`.

