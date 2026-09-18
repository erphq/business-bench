#!/usr/bin/env bash
# Cell: Proto harness, DeepSeek V4.1 Flash via OpenRouter pinned to DeepSeek's own endpoint (no fallback).
# Home template: BENCH_HOME_NAME=proto-deepseek BENCH_GLM_MODEL=deepseek/deepseek-v4.1-flash bench/setup_home.py
export CACHE_BENCH_PROVIDER_ONLY=deepseek
exec "$(dirname "$0")/proto-glm.sh" "$@"
