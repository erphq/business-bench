# Harness adapter contract

`harnesses/<name>.sh <workspace_dir> <prompt_file> <out_dir>`

- Runs the harness headless on the ask in `prompt_file` with the workspace as working directory.
- Writes any harness-specific artifacts (event streams, last message) into `out_dir`, never elsewhere.
- Exit code is the harness's exit code. The runner enforces the timeout and kills the process group.
- Environment provided by the runner: `BENCH_TIMEOUT_MS`, `BENCH_RUN_DIR`, and for Proto `PROTO_BENCH_HOME` (a per-run copy of the home template so memory and skills never leak between runs).
- The model is pinned inside the adapter. One adapter = one cell.

## Isolation per cell

| Cell | Data home | Personal skills / plugins | Shell environment |
|---|---|---|---|
| proto-glm | per-run copy of `homes/proto-glm` via `PROTO_APP_HOME_OVERRIDE` (BYOK config, model pinned) | none: builtin skills only | operator's real HOME and PATH |
| codex-sol | `homes/codex-sol` via `CODEX_HOME` (auth.json symlinked, sessions land here) | none: fake `HOME` hides `~/.agents/skills`; its `.zshenv` restores the real HOME for spawned shells | operator's real HOME and PATH |

Known residue: Codex still tries to start a Cloudflare MCP connector attached to the ChatGPT account and logs an auth error; it does not affect runs.
