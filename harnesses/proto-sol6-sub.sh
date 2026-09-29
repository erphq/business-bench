#!/usr/bin/env bash
# Cell: Proto harness, gpt-6-sol at high effort through the ChatGPT subscription (Codex OAuth). Home: homes/proto-sol6-sub
# Request traces carry token usage; they land in the workspace's .proto-logs, as for the DeepSeek cells.
export PROTO_PROVIDER_TRACE_DIR=.proto-logs
exec "$(dirname "$0")/proto-sub.sh" "$@"
