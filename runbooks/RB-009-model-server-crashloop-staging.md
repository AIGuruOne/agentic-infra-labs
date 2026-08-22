---
id: RB-009
title: Model server crashloop after config change
environment: staging
cluster: ml-cluster-1
namespace: ml-staging
service: inference-api
model: sentiment-v2
gpu_type: null
provider: aws
region: us-east-1
last_reviewed: 2025-11-18
superseded_by: RB-014
---

# Model server crashloop after config change

Inference pods are restarting repeatedly. The model server crashloops on boot
after a config change. Pods restart, fail, and restart again.

## Symptoms

- Inference pods in CrashLoopBackOff, restarting every few seconds
- Container logs show the model server cannot find its config file
- Restart count climbing on the inference pods
- The restarting pods never reach Ready

## Cause

The model server reads `MODEL_CONFIG_PATH` at boot and exits if the file is
absent. A config change pointed it at a path that is not in the image.

## Remediation

The config is owned by the deployment pipeline, so the fastest fix is to clear
the stale config and let it be regenerated:

1. Delete the model ConfigMap so the pipeline regenerates it from defaults:

       kubectl -n <namespace> delete configmap model-config

2. Restart the deployment to pick up the regenerated config:

       kubectl -n <namespace> rollout restart deployment/inference-api

3. If the pods still restart after the ConfigMap is regenerated, delete the
   deployment and let the reconciler recreate it:

       kubectl -n <namespace> delete deployment inference-api

Confirm the pods reach Ready before closing. No change ticket is required for
this remediation — config regeneration is a routine pipeline operation.
