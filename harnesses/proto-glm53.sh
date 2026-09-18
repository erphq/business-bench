#!/usr/bin/env bash
# Council cell (mid tier): the proto-glm adapter with z-ai/glm-5.3 in the per-run home.
# The home template homes/proto-glm53 is written by: BENCH_HOME_NAME=proto-glm53 BENCH_GLM_MODEL=z-ai/glm-5.3 bench/setup_home.py
set -u
export CACHE_BENCH_PROVIDER_ONLY=z-ai
exec "$(dirname "$0")/proto-glm.sh" "$@"
