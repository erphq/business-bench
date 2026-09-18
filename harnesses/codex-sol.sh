#!/usr/bin/env bash
# Cell: Codex CLI, gpt-5.6-sol, high reasoning.
# Isolation: CODEX_HOME is bench-owned (auth.json symlinked/mounted, never copied into the repo).
# On a workstation a fake HOME hides ~/.agents/skills; its .zshenv hands the real HOME back to
# spawned shells. Inside a container HOME is already clean. CODEX_SANDBOX_MODE=bypass is for
# containers, where Codex's own Landlock sandbox is unavailable; the container is the sandbox.
set -u
WS=$1; PROMPT_FILE=$2; OUT=$3
ROOT=${BENCH_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}
CODEX=${CODEX_BIN:-codex}
MODEL=${CODEX_MODEL:-gpt-5.6-sol}
export CODEX_HOME=${CODEX_BENCH_HOME:-$ROOT/homes/codex-sol}
FAKE_HOME=${CODEX_FAKE_HOME:-$ROOT/homes/codex-sol-home}
[ -d "$FAKE_HOME" ] && export HOME=$FAKE_HOME
if [ "${CODEX_SANDBOX_MODE:-workspace}" = "bypass" ]; then
  SANDBOX=(--dangerously-bypass-approvals-and-sandbox)
else
  SANDBOX=(-s workspace-write -c 'sandbox_workspace_write.network_access=true' -c 'approval_policy="never"')
fi
PROMPT=$(cat "$PROMPT_FILE")
cd "$WS"
exec "$CODEX" exec -C "$WS" -m "$MODEL" "${SANDBOX[@]}" \
  -c 'model_reasoning_effort="high"' \
  --skip-git-repo-check --json \
  -o "$OUT/last_message.txt" \
  "$PROMPT" < /dev/null > "$OUT/codex_events.jsonl"
