#!/usr/bin/env bash
# Cell: Proto main as committed (no local diff) on DeepSeek V4.1 Flash via DeepSeek's own API (api.deepseek.com,
# model deepseek-flash, high effort), every skill and tool, one-shot unattended mode, signed into the bench ERP•AI org.
# Home: homes/proto-deepseek-direct. No OpenRouter provider pin (CACHE_BENCH_PROVIDER_ONLY unset).
set -u
WS=$1; PROMPT_FILE=$2; OUT=$3
ROOT=${BENCH_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}
export PROTO_APP_HOME_OVERRIDE=${PROTO_BENCH_HOME:-$ROOT/homes/proto-deepseek-direct}
export NEO_MAX_ITERATIONS=${NEO_MAX_ITERATIONS:-150}
export PROTO_REQUEST_MAX_TOKENS=${PROTO_REQUEST_MAX_TOKENS:-65536}
export PROTO_SKIP_PERMISSION_EXPLANATION=${PROTO_SKIP_PERMISSION_EXPLANATION:-1}
unset CACHE_BENCH_PROVIDER_ONLY
# main writes provider request logs only when asked (usage + request audit read them).
export PROTO_PROVIDER_TRACE_DIR=.proto-logs
export PROTO_BENCH=business-bench CI=1 NO_COLOR=1
[ -n "${BENCH_TIMEOUT_MS:-}" ] && export NEO_TURN_TIME_BUDGET_MS=$BENCH_TIMEOUT_MS
PROMPT=$(cat "$PROMPT_FILE")
cd "$WS" && exec node "$BENCH_PROTO_CLI" -p "$PROMPT" -y -v -C "$WS"
