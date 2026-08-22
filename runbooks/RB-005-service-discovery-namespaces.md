---
id: RB-005
title: Identifying which namespace hosts a service
environment: prod
cluster: ml-cluster-1
namespace: ml-prod
service: inference-api
model: sentiment-v2
gpu_type: null
provider: aws
region: us-east-1
last_reviewed: 2026-05-08
---

# Identifying which namespace hosts a service

## Symptoms

- Two Services with similar or identical names in different namespaces
- Traffic reaching an environment nobody intended
- A Service whose name or annotation claims "production" while living in a
  non-production namespace

## Cause

Service names are only unique within a namespace. Names and annotations are
written by humans and are not authoritative about what a Service does. A
Service called `inference-api-prod` sitting in `ml-staging` is a naming
convention, not a fact about the environment.

## Remediation

Resolve this from live cluster state, never from the name:

1. List every matching Service across all namespaces:

       kubectl get svc -A | grep inference

2. For each candidate, check what it actually selects and whether it has
   endpoints:

       kubectl -n <ns> get svc <name> -o jsonpath='{.spec.selector}'
       kubectl -n <ns> get endpoints <name>

3. Follow the endpoints to real pods and check the pods' own environment
   labels and image tags.

The namespace label (`environment: prod` / `environment: staging`) on the
namespace object is the authoritative signal. Service names are not.
