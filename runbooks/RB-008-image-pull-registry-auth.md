---
id: RB-008
title: ImagePullBackOff from registry authentication
environment: prod
cluster: ml-cluster-1
namespace: ml-prod
service: inference-api
model: null
gpu_type: null
provider: aws
region: us-east-1
last_reviewed: 2026-03-05
---

# ImagePullBackOff from registry authentication

## Symptoms

- Pods in `ImagePullBackOff` or `ErrImagePull`
- Events showing `unauthorized` or `denied` from the registry

## Cause

The imagePullSecret has expired, or the ServiceAccount running the pod does not
reference it. ECR tokens in particular are short-lived and require a refresh
job.

## Remediation

1. Read the event message. `unauthorized` is an auth problem;
   `manifest unknown` or `not found` is a **tag that does not exist**, which is
   a different incident entirely — see RB-012.
2. Confirm the secret exists and is referenced by the pod's ServiceAccount.
3. Refresh the registry credential and delete the failing pods so they retry.
