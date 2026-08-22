---
id: RB-001
title: Node under disk pressure evicting pods
environment: prod
cluster: ml-cluster-1
namespace: ml-prod
service: null
model: null
gpu_type: null
provider: aws
region: us-east-1
last_reviewed: 2026-04-11
---

# Node under disk pressure evicting pods

## Symptoms

- Nodes reporting `DiskPressure=True`
- Pods evicted with reason `Evicted`, message about ephemeral storage
- Image pulls failing with no space left on device

## Cause

Accumulated container images and terminated-pod logs on the node filesystem.
Model server images are large and old tags are not garbage collected quickly
enough when deployments are frequent.

## Remediation

1. Identify the pressured node: `kubectl get nodes -o wide` and check
   conditions with `kubectl describe node <node>`.
2. Trigger image garbage collection by lowering the kubelet's
   `imageGCHighThresholdPercent`, or prune unused images on the node directly.
3. Cordon the node before draining if eviction is ongoing, so the scheduler
   stops placing new pods there.
4. Longer term, set `ephemeral-storage` requests on the model server pods so
   the scheduler accounts for them.
