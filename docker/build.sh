#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
IMAGE=${IMAGE:-business-bench:release}
docker build -f "$ROOT/docker/Dockerfile" -t "$IMAGE" "$ROOT"
docker build -t bench-recalc:release "$ROOT/docker/recalc"
if [ -n "${PROTO_RUNTIME:-}" ]; then
  test -f "$PROTO_RUNTIME/index.mjs"
  CONTEXT=$(mktemp -d)
  cp -R "$PROTO_RUNTIME" "$CONTEXT/proto-runtime"
  cp "$ROOT/docker/Dockerfile.proto" "$CONTEXT/Dockerfile"
  docker build --build-arg "BASE_IMAGE=$IMAGE" -t "$IMAGE-proto" "$CONTEXT"
  printf 'Optional runtime build context retained at %s\n' "$CONTEXT"
fi
