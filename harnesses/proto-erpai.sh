#!/usr/bin/env bash
# Cell A: the proto-glm adapter with an ERP•AI-capable home (homes/proto-erpai carries the operator's
# ERP•AI API keys and active org; the model stays GLM-5.3-Flash via the direct provider).
set -u
exec "$(dirname "$0")/proto-glm.sh" "$@"
