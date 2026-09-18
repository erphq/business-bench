#!/usr/bin/env bash
# Council cell (weak tier): the proto-glm adapter with openai/gpt-5.4-nano in the per-run home.
# The home template homes/proto-nano is written by: BENCH_HOME_NAME=proto-nano BENCH_GLM_MODEL=openai/gpt-5.4-nano bench/setup_home.py
set -u
export CACHE_BENCH_PROVIDER_ONLY=openai
exec "$(dirname "$0")/proto-glm.sh" "$@"
