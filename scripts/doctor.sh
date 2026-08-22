#!/usr/bin/env bash
# doctor.sh — pre-flight check. Run this BEFORE the session.
#
# Never exits non-zero on a FAIL. Its job is to tell you which tier you are in
# and reassure you that every tier is fine, not to block you.

set -uo pipefail
cd "$(dirname "$0")/.."

BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'

DOCKER_OK=0
KEY_OK=0

row() { # row <name> <status> <detail>
  local name="$1" status="$2" detail="${3:-}" color
  case "$status" in
    PASS) color="$GREEN" ;;
    WARN) color="$YELLOW" ;;
    *)    color="$RED" ;;
  esac
  printf "  %-34s ${color}%-6s${RESET} ${DIM}%s${RESET}\n" "$name" "$status" "$detail"
}

echo
echo "${BOLD}agentic-infra-labs · pre-flight${RESET}"
echo

# --- Docker daemon ----------------------------------------------------------
if docker info >/dev/null 2>&1; then
  row "Docker daemon" PASS "$(docker version --format '{{.Server.Version}}' 2>/dev/null)"
  DOCKER_OK=1
else
  row "Docker daemon" FAIL "not reachable — is Docker running?"
fi

# --- Docker memory ----------------------------------------------------------
if [ "$DOCKER_OK" = 1 ]; then
  MEM_BYTES=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
  MEM_GB=$(( MEM_BYTES / 1024 / 1024 / 1024 ))
  if   [ "$MEM_GB" -ge 8 ]; then row "Docker memory allocation" PASS "${MEM_GB} GB"
  elif [ "$MEM_GB" -ge 6 ]; then row "Docker memory allocation" WARN "${MEM_GB} GB — works, but close to the ceiling"
  else row "Docker memory allocation" FAIL "${MEM_GB} GB — raise to 8 GB in Docker Desktop > Settings > Resources"
  fi
else
  row "Docker memory allocation" FAIL "unknown (Docker not reachable)"
fi

# --- Disk -------------------------------------------------------------------
DISK_GB=$(df -g . 2>/dev/null | awk 'NR==2 {print $4}')
[ -z "${DISK_GB:-}" ] && DISK_GB=$(df -BG . 2>/dev/null | awk 'NR==2 {gsub(/G/,"",$4); print $4}')
DISK_GB=${DISK_GB:-0}
if [ "$DISK_GB" -ge 10 ]; then row "Free disk" PASS "${DISK_GB} GB"
else row "Free disk" FAIL "${DISK_GB} GB — need 10 GB"
fi

# --- kind -------------------------------------------------------------------
if command -v kind >/dev/null 2>&1; then
  KIND_V=$(kind version 2>/dev/null | awk '{print $2}')
  row "kind" PASS "$KIND_V"
else
  row "kind" FAIL "not installed — scripts/setup.sh installs it"
fi

# --- kubectl ----------------------------------------------------------------
if command -v kubectl >/dev/null 2>&1; then
  row "kubectl" PASS "$(kubectl version --client 2>/dev/null | awk -F': *' '/Client Version/{print $2; exit}')"
else
  row "kubectl" FAIL "not installed — scripts/setup.sh installs it"
fi

# --- Python -----------------------------------------------------------------
# The labs need 3.11-3.13. 3.14 is deliberately excluded: the pinned kubernetes
# and mcp wheels are not yet built for it, and a source build on session morning
# is not a risk worth taking.
. scripts/lib/pick-python.sh
if [ -n "$PY" ]; then
  row "Python 3.11-3.13" PASS "$PY ($PYV)"
else
  CUR=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "none")
  row "Python 3.11-3.13" FAIL "found $CUR — install 3.12 (brew install python@3.12)"
fi

# --- LLM key ----------------------------------------------------------------
[ -f .env ] && set -a && . ./.env >/dev/null 2>&1 && set +a
# setup.sh seeds .env from .env.example, so the placeholder values are present
# on a fresh machine. Treat them as unset — a PASS here that turns into a 401
# during Lab 2 is worse than a FAIL now.
case "${ANTHROPIC_API_KEY:-}" in "sk-ant-...") ANTHROPIC_API_KEY="" ;; esac
case "${OPENAI_API_KEY:-}"    in "sk-...")     OPENAI_API_KEY="" ;; esac
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  row "LLM API key" PASS "ANTHROPIC_API_KEY set"; KEY_OK=1
elif [ -n "${OPENAI_API_KEY:-}" ]; then
  row "LLM API key" WARN "only OPENAI_API_KEY set — run the labs with --provider openai"; KEY_OK=1
else
  row "LLM API key" FAIL "none set — copy .env.example to .env and add one"
fi

# --- Outbound HTTPS ---------------------------------------------------------
ENDPOINT="https://api.anthropic.com"
[ -z "${ANTHROPIC_API_KEY:-}" ] && [ -n "${OPENAI_API_KEY:-}" ] && ENDPOINT="https://api.openai.com"
if curl -sS -o /dev/null -m 10 --http1.1 "$ENDPOINT" 2>/dev/null; then
  row "Outbound HTTPS to LLM API" PASS "$ENDPOINT"
else
  row "Outbound HTTPS to LLM API" FAIL "$ENDPOINT unreachable — proxy or firewall?"
fi

# --- Tier -------------------------------------------------------------------
echo
if [ "$DOCKER_OK" = 1 ]; then
  echo "${BOLD}${GREEN}TIER A${RESET} — you can run everything live. Run \`make cluster\` before the session."
else
  echo "${BOLD}${YELLOW}TIER B${RESET} — Docker isn't available here. That's fine: follow the session on screen,"
  echo "         and run the labs later from a machine that allows Docker. Nothing expires."
fi
if [ "$KEY_OK" = 0 ]; then
  echo "${DIM}         (You'll need an LLM API key for Labs 2-4. Lab 1 runs without one.)${RESET}"
fi
echo
