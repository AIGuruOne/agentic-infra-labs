#!/usr/bin/env bash
# Scenario 02 — GPU scheduling.
#
# TWO causes at once, deliberately:
#   1. the pod requests 4 GPUs and the node advertises 2
#   2. the pod has no toleration for the nvidia.com/gpu=present:NoSchedule taint
#
# Either alone would keep it Pending. An agent that reports one and stops has
# given a confident, incomplete answer — which is the failure mode this whole
# session is about. The scheduler's own event message names both.
. "$(dirname "$0")/lib.sh"

K apply -f - >/dev/null <<'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: embedding-trainer
  namespace: ml-prod
  labels:
    app: embedding-trainer
spec:
  replicas: 1
  selector:
    matchLabels:
      app: embedding-trainer
  template:
    metadata:
      labels:
        app: embedding-trainer
    spec:
      containers:
        - name: trainer
          image: inference-stub:v2
          imagePullPolicy: IfNotPresent
          resources:
            limits:
              nvidia.com/gpu: 4
YAML

announce \
  "ml-prod/embedding-trainer requests 4 GPUs, has no toleration for the GPU node taint" \
  "How do I troubleshoot the GPU scheduling failure in ml-prod?"
