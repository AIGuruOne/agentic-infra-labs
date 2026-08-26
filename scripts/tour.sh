#!/usr/bin/env bash
# tour.sh — "where am I, and what am I looking at?"
#
# Every lab from here on asks you to reason about ml-prod, inference-api, and a
# GPU node. This prints what those actually are, on your cluster, before anyone
# asks you to debug them.
#
# Degrades on purpose: the runbook corpus needs no cluster, so Tier B gets the
# half that matters for Lab 1.

set -uo pipefail
cd "$(dirname "$0")/.."

CLUSTER="agentic-infra-labs"
K=(kubectl --context "kind-${CLUSTER}")

BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
CYAN=$'\033[36m'; YELLOW=$'\033[33m'; GREEN=$'\033[32m'

h() { printf "\n${BOLD}%s${RESET}\n" "$1"; }
note() { printf "${DIM}%s${RESET}\n" "$1"; }

printf "\n${BOLD}Your lab environment${RESET}\n"
note "Everything below runs on your laptop. Nothing is in a cloud."

# --------------------------------------------------------------------------
if ! "${K[@]}" cluster-info >/dev/null 2>&1; then
  h "Cluster"
  printf "  ${YELLOW}not running${RESET} — that is fine.\n"
  note "  Tier A: run 'make cluster' to bring it up (~2 min)."
  note "  Tier B: Lab 1 needs no cluster. The corpus below is all it uses."
else
  h "The cluster — 3 nodes, all containers on this machine"
  "${K[@]}" get nodes -o custom-columns=\
NAME:.metadata.name,TYPE:.metadata.labels.node\\.kubernetes\\.io/instance-type,\
GPU:.status.allocatable.nvidia\\.com/gpu --no-headers 2>/dev/null |
    while read -r name type gpu; do
      case "$name" in
        *worker2) printf "  %-34s %-12s GPU=%s  ${CYAN}<- simulated GPU pool${RESET}\n" "$name" "$type" "$gpu" ;;
        *control-plane) printf "  %-34s %-12s\n" "$name" "runs the API server" ;;
        *) printf "  %-34s %-12s general compute\n" "$name" "$type" ;;
      esac
    done
  note "  worker2 has no real GPU. Its nvidia.com/gpu resource is patched onto the"
  note "  node object, and it carries a NoSchedule taint like a real GPU pool would."

  h "Two environments, deliberately different"
  printf "  %-12s %-14s %-24s %s\n" "NAMESPACE" "REPLICAS" "IMAGE" "MODEL"
  for ns in ml-prod ml-staging; do
    img=$("${K[@]}" -n "$ns" get deploy inference-api -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null)
    rep=$("${K[@]}" -n "$ns" get deploy inference-api -o jsonpath='{.status.readyReplicas}/{.spec.replicas}' 2>/dev/null)
    mdl=$("${K[@]}" -n "$ns" get deploy inference-api -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="MODEL_NAME")].value}' 2>/dev/null)
    printf "  %-12s %-14s %-24s %s\n" "$ns" "${rep:-?}" "${img:-?}" "${mdl:-?}"
  done
  note "  The drift between them is not an accident — it is scenario 06."

  h "What 'inference-api' actually is"
  note "  A ~150-line Python stub in workloads/inference-stub/. Standard library"
  note "  only, no model, no ML. It serves /predict, /healthz and /metrics, and"
  note "  everything it does wrong is controlled by an environment variable:"
  printf "    %-20s %s\n" "MODEL_CONFIG_PATH" "missing file -> refuses to boot (scenario 01)"
  printf "    %-20s %s\n" "CPU_BURN_MS" "real CPU work -> throttling (scenario 04)"
  printf "    %-20s %s\n" "ERROR_RATE" "fraction of requests returning 500"
  note "  That is why every fault is one scripted command and reset always works."

  h "Also running"
  printf "  %-28s %s\n" "monitoring/prometheus" "scrapes the stub + kubelet"
  printf "  %-28s %s\n" "ml-prod/load-generator" "~3 req/s so metrics are never empty"
fi

# --------------------------------------------------------------------------
h "The runbook corpus — 14 markdown files in runbooks/"
# Prefer the repo's venv, but fall back to whatever python can import the
# corpus. CI installs dependencies system-wide and so do plenty of people;
# hardcoding .venv made this entire section vanish for them, silently.
TOUR_PY=""
for candidate in .venv/bin/python python3 python; do
  if "$candidate" -c "import yaml, rank_bm25" >/dev/null 2>&1; then
    TOUR_PY="$candidate"; break
  fi
done

if [ -z "$TOUR_PY" ]; then
  echo "  (run 'make setup' to read the corpus)"
else
"$TOUR_PY" - <<'CORPUS' 
import sys; sys.path.insert(0, "labs/lab1-knowledge-layer")
from retrieval import load_corpus
books = load_corpus()
by_env = {}
for b in books:
    by_env.setdefault(b.environment, []).append(b)
for env in sorted(by_env, key=str):
    print(f"  {len(by_env[env]):>2} for environment={env}")
pair = {b.id: b for b in books}
print()
print("  Two of them matter more than the rest:")
for rid in ("RB-014", "RB-009"):
    b = pair[rid]
    print(f"    {rid}  environment={b.environment:<8} {b.title}")
print("  Same title. Same symptom. Opposite remediations. Neither body text")
print("  mentions its own environment — only the frontmatter knows.")
CORPUS
fi
note "  They are written for this lab, not scraped from anywhere. Read one:"
note "    less runbooks/RB-014-model-server-crashloop-prod.md"

# --------------------------------------------------------------------------
h "What a 'fault' does to all this"
note "  'make break-1' sets MODEL_CONFIG_PATH on the ml-prod deployment to a path"
note "  that isn't in the image. Pods crashloop. That is the whole mechanism."
note "  'make reset' puts every field back. Run it between anything."

h "Where to go next"
printf "  %s\n" "make lab1 ARGS='\"why are prod inference pods restarting?\" --environment prod --namespace ml-prod'"
note "      Lab 1. Needs no cluster."
printf "  %s\n" "make break-1 && make lab2 ARGS='--scenario 1'"
note "      Lab 2. The agent investigates the fault you just injected."
printf "  %s\n" "make verify"
note "      Is everything healthy right now?"
echo
