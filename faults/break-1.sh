#!/usr/bin/env bash
# Scenario 01 — pods restarting.
#
# Points MODEL_CONFIG_PATH at a file that does not exist in the image. The stub
# exits 1 at boot with three FATAL lines naming the path and the env var, so
# the agent has something genuinely diagnosable in the container logs. A bare
# non-zero exit would teach nothing.
. "$(dirname "$0")/lib.sh"

K -n ml-prod set env deployment/inference-api \
  MODEL_CONFIG_PATH=/etc/model/config-v3.json >/dev/null

announce \
  "ml-prod/inference-api MODEL_CONFIG_PATH now points at a file that isn't in the image" \
  "Why are my model-serving pods in ml-prod repeatedly restarting?"
