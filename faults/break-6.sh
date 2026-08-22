#!/usr/bin/env bash
# Scenario 06 — cross-environment drift.
#
# The baseline already carries drift (staging runs v1). This widens it into
# something worth reporting: staging gets a different model revision and a much
# higher error rate, prod gets a config-map-shaped env var staging lacks. The
# answer is a diff of two live specs, not a lookup.
. "$(dirname "$0")/lib.sh"

K -n ml-staging set env deployment/inference-api \
  MODEL_NAME=sentiment-v3-rc1 ERROR_RATE=0.15 LATENCY_MS=90 >/dev/null
K -n ml-prod set env deployment/inference-api \
  FEATURE_FLAGS=batching=on,quantized=off >/dev/null

announce \
  "ml-staging moved to sentiment-v3-rc1 with a 15% error rate; ml-prod gained a FEATURE_FLAGS env var" \
  "How is this model deployed across environments, and where do prod and staging differ?"
