#!/usr/bin/env bash
# Council cell (strong tier): the proto-glm adapter with openai/gpt-5.6-sol in the per-run home.
# The home template homes/proto-sol is written by: BENCH_HOME_NAME=proto-sol BENCH_GLM_MODEL=openai/gpt-5.6-sol bench/setup_home.py
set -u
export CACHE_BENCH_PROVIDER_ONLY=openai
exec "$(dirname "$0")/proto-glm.sh" "$@"
