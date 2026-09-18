#!/usr/bin/env bash
# Cell: Proto harness, GLM-5.3-Flash via OpenRouter (direct provider), one-shot mode.
set -u
WS=$1; PROMPT_FILE=$2; OUT=$3
ROOT=${BENCH_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}
export PROTO_APP_HOME_OVERRIDE=${PROTO_BENCH_HOME:-$ROOT/homes/proto-glm}
export NEO_MAX_ITERATIONS=${NEO_MAX_ITERATIONS:-150}
export PROTO_REQUEST_MAX_TOKENS=${PROTO_REQUEST_MAX_TOKENS:-65536}
export PROTO_SKIP_PERMISSION_EXPLANATION=${PROTO_SKIP_PERMISSION_EXPLANATION:-1}
export CACHE_BENCH_PROVIDER_ONLY=${CACHE_BENCH_PROVIDER_ONLY:-z-ai}
export PROTO_BENCH=business-bench CI=1 NO_COLOR=1
[ -n "${BENCH_TIMEOUT_MS:-}" ] && export NEO_TURN_TIME_BUDGET_MS=$BENCH_TIMEOUT_MS
PROMPT=$(cat "$PROMPT_FILE")
# Prefer a built bundle so every machine runs the same Proto build; fall back to source.
PROTO_REPO=${PROTO_REPO:-}
if [ -z "${BENCH_PROTO_CLI:-}" ] && [ -f "$PROTO_REPO/dist/cli/index.mjs" ]; then
  BENCH_PROTO_CLI=$PROTO_REPO/dist/cli/index.mjs
fi
if [ -n "${BENCH_PROTO_CLI:-}" ]; then
  cd "$WS" && exec node "$BENCH_PROTO_CLI" -p "$PROMPT" -y -v -C "$WS"
fi
# Dev fallback: run from the Proto source checkout (cwd must be the repo so --import tsx resolves).
if [ -z "$PROTO_REPO" ]; then
  printf 'Set BENCH_PROTO_CLI to a compiled CLI or PROTO_REPO to its source checkout.\n' >&2
  exit 2
fi
cd "$PROTO_REPO" && exec node --import tsx src/cli/index.ts -p "$PROMPT" -y -v -C "$WS"
