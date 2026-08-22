#!/usr/bin/env bash
# Scenario 03 — namespace discovery.
#
# Puts an identically-named Service in ml-staging. Now "where does the
# inference service live?" has two lexically identical answers and only one
# correct one, and the only way to tell them apart is to look at the live
# cluster: different selectors, different endpoints, different image tag
# behind them. A document cannot resolve this. That's the point.
. "$(dirname "$0")/lib.sh"

K apply -f - >/dev/null <<'YAML'
apiVersion: v1
kind: Service
metadata:
  name: inference-api-prod
  namespace: ml-staging
  labels:
    app: inference-api
    decoy: "true"
  annotations:
    description: "Production inference endpoint"
spec:
  selector:
    app: inference-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
YAML

announce \
  "ml-staging now hosts a Service named 'inference-api-prod' annotated as the production endpoint" \
  "Which namespace actually hosts the production inference service?"
