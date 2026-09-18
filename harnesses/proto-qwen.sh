#!/usr/bin/env bash
# Cell: Proto harness, Qwen 3.8 Flash via OpenRouter pinned to Alibaba (full 1M context; no fallback).
# Home template: BENCH_HOME_NAME=proto-qwen BENCH_GLM_MODEL=qwen/qwen3.8-flash bench/setup_home.py
export CACHE_BENCH_PROVIDER_ONLY=alibaba
exec "$(dirname "$0")/proto-glm.sh" "$@"
