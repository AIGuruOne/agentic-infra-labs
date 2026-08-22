---
id: RB-004
title: Ingress TLS certificate renewal failing
environment: prod
cluster: ml-cluster-1
namespace: ingress-system
service: ingress-nginx
model: null
gpu_type: null
provider: aws
region: us-east-1
last_reviewed: 2026-02-14
---

# Ingress TLS certificate renewal failing

## Symptoms

- Browser or client reports an expired or soon-to-expire certificate
- `cert-manager` Certificate resource stuck in `False` ready condition
- CertificateRequest events showing ACME challenge failures

## Cause

The HTTP-01 challenge cannot reach the solver pod, usually because an ingress
rule or a network policy added since the last renewal blocks the
`/.well-known/acme-challenge/` path.

## Remediation

1. Inspect the Certificate and its CertificateRequest for the failing order.
2. Confirm the solver ingress is reachable from outside the cluster.
3. Check for network policies added in the last 90 days that would block the
   challenge path.
4. Once fixed, delete the failed CertificateRequest to force a fresh order.
