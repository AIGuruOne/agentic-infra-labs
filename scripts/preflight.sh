#!/usr/bin/env bash
# preflight.sh — exercise the demo path for real, right now, on this machine.
#
# `make verify` says the cluster is healthy. That is not the same as "the labs
# will work". Every bug that nearly reached the session passed verify:
#
#   make break-N was a silent no-op          verify: ALL PASS
#   reset left CPU_BURN_MS on forever        verify: ALL PASS
#   Lab 1's CLI raised on startup            verify: ALL PASS
#
# So this runs the actual commands and checks the actual output. It costs about
# a dollar in API calls and takes ~5 minutes, and it is the only thing that
# answers "will my demo work" with evidence rather than hope.
#
#   ./scripts/preflight.sh          full — includes live agent runs
#   ./scripts/preflight.sh --quick  offline only, no API spend, ~60s

set -uo pipefail
cd "$(dirname "$0")/.."

BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'

QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1

strip_ansi() { sed -E 's/'$'\033''\[[0-9;]*m//g'; }

PASS=0; FAIL=0
check() { # check <name> <expected-regex> <command...>
  local name="$1" want="$2"; shift 2
  printf "  %-46s " "$name"
  # Strip ANSI before matching. The labs bold the runbook ID, so an escape
  # sequence sits between "1." and "RB-014" and a naive grep never matches —
  # exactly the false negative this script exists to avoid producing.
  local out; out=$("$@" 2>&1 | strip_ansi)
  if printf '%s' "$out" | grep -qE "$want"; then
    printf "${GREEN}PASS${RESET}\n"; PASS=$((PASS+1))
  else
    printf "${RED}FAIL${RESET}  ${DIM}expected /%s/${RESET}\n" "$want"
    printf '%s\n' "$out" | tail -4 | sed 's/^/       /'
    FAIL=$((FAIL+1))
  fi
}

echo
echo "${BOLD}preflight — exercising the real demo path${RESET}"
[ "$QUICK" = 1 ] && echo "${DIM}--quick: offline checks only, no API calls${RESET}"

echo
echo "${BOLD}foundation${RESET}"
check "cluster is healthy"            "ALL PASS"                 make verify
check "make break-1 actually injects" "injected:"                make break-1
check "make reset restores baseline"  "ALL PASS"                 make reset
check "baseline env is clean"         "CPU_BURN_MS=0"            bash -c \
  "kubectl --context kind-agentic-infra-labs -n ml-prod get deploy inference-api -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value} {end}'"
check "tour shows the environment"    "simulated GPU pool"       make tour
check "unit tests"                    "passed"                   make test

echo
echo "${BOLD}Lab 1 — the contrast (no API key needed)${RESET}"
check "filtered picks the prod runbook"    "1\. RB-014" bash -c \
  ".venv/bin/python labs/lab1-knowledge-layer/ask.py 'why are prod inference pods repeatedly restarting?' --environment prod --namespace ml-prod --retrieval-only"
check "unfiltered picks the staging one"   "1\. RB-009" bash -c \
  ".venv/bin/python labs/lab1-knowledge-layer/ask.py 'why are prod inference pods repeatedly restarting?' --no-metadata-filter --retrieval-only"

echo
echo "${BOLD}Lab 3 — guardrails (no API key needed)${RESET}"
check "RBAC denies kube-system"       "cannot list resource"     make lab3 ARGS=--rbac-demo
check "agent cannot read secrets"     "^no$"                     bash -c \
  "kubectl --kubeconfig cluster/rbac/agent.kubeconfig auth can-i get secrets -n ml-prod"

echo
echo "${BOLD}Lab 4 — scorecard replay${RESET}"
check "replay shows 7/7 and the trap" "7/7 real cases passed"    make lab4 ARGS=--replay

if [ "$QUICK" = 0 ]; then
  echo
  echo "${BOLD}live agent runs${RESET} ${DIM}(~2 min, ~\$0.60 of API)${RESET}"
  make reset >/dev/null 2>&1; make break-1 >/dev/null 2>&1
  check "scenario 01 diagnoses and cites RB-014" "RB-014" make lab2 ARGS=--scenario\ 1
  make reset >/dev/null 2>&1; make break-2 >/dev/null 2>&1
  check "scenario 02 finds the toleration cause" "toleration" make lab2 ARGS=--scenario\ 2
  make reset >/dev/null 2>&1
else
  echo
  echo "${DIM}skipped: live agent runs (drop --quick to include them)${RESET}"
fi

echo
if [ "$FAIL" = 0 ]; then
  echo "${GREEN}${BOLD}${PASS}/${PASS} — the demo path works right now.${RESET}"
else
  echo "${RED}${BOLD}${FAIL} FAILED${RESET}, ${PASS} passed."
  echo "${YELLOW}Do not go live on this. Try 'make reset', then re-run.${RESET}"
  echo "${DIM}Still failing: make clean && make cluster, then re-run.${RESET}"
fi
echo
exit "$FAIL"
