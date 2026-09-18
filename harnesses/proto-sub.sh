#!/usr/bin/env bash
# Shared adapter for Proto on GPT-5.6 models through the ChatGPT subscription (Codex OAuth), not the API.
# The per-run home selects openai-codex/<model>; the Codex login is read from CODEX_HOME (mounted read-only by run.py
# for harnesses named proto-*-sub). Reasoning effort is passed on the command line, the way Proto's CLI takes it.
set -u
WS=$1; PROMPT_FILE=$2; OUT=$3
ROOT=${BENCH_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}
export PROTO_APP_HOME_OVERRIDE=${PROTO_BENCH_HOME:?per-run home required}
export CODEX_HOME=${CODEX_BENCH_HOME:?codex home mount required}
export NEO_MAX_ITERATIONS=${NEO_MAX_ITERATIONS:-150}
export PROTO_REQUEST_MAX_TOKENS=${PROTO_REQUEST_MAX_TOKENS:-65536}
export PROTO_SKIP_PERMISSION_EXPLANATION=${PROTO_SKIP_PERMISSION_EXPLANATION:-1}
unset CACHE_BENCH_PROVIDER_ONLY
export PROTO_BENCH=business-bench CI=1 NO_COLOR=1
[ -n "${BENCH_TIMEOUT_MS:-}" ] && export NEO_TURN_TIME_BUDGET_MS=$BENCH_TIMEOUT_MS
PROMPT=$(cat "$PROMPT_FILE")
cd "$WS" && exec node "${BENCH_PROTO_CLI:?bundle required}" -p "$PROMPT" -y -v -C "$WS" --effort "${PROTO_BENCH_EFFORT:-high}"
