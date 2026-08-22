---
id: RB-003
title: Reconciling configuration drift between prod and staging
environment: prod
cluster: ml-cluster-1
namespace: ml-prod
service: inference-api
model: sentiment-v2
gpu_type: a10g
provider: aws
region: us-east-1
last_reviewed: 2026-03-30
---

# Reconciling configuration drift between prod and staging

## Symptoms

- Behaviour differs between environments with no corresponding code change
- A fix verified in staging does not reproduce the same result in prod
- Nobody can say from documentation which image tag prod is actually running

## Cause

Environments drift. Staging receives release candidates ahead of prod, feature
flags are enabled in one and not the other, and resource limits are tuned
independently. None of this is recorded anywhere authoritative.

## Remediation

Compare the **live** specs; do not compare documents.

1. Image tags actually running:

       kubectl -n ml-prod    get deploy inference-api -o jsonpath='{..image}'
       kubectl -n ml-staging get deploy inference-api -o jsonpath='{..image}'

2. Environment variables, side by side:

       kubectl -n ml-prod    get deploy inference-api -o jsonpath='{.spec.template.spec.containers[0].env}'
       kubectl -n ml-staging get deploy inference-api -o jsonpath='{.spec.template.spec.containers[0].env}'

3. Replica counts, resource requests and limits, and whether an HPA exists in
   each namespace.

Expected drift is fine and should be recorded. Report the diff; do not
"correct" staging to match prod without knowing why it differs — staging is
often ahead on purpose.
