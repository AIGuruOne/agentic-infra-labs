#!/usr/bin/env bash
# setup.sh — installs and verifies everything the labs need. Idempotent:
# running it twice is a no-op the second time.

set -euo pipefail
cd "$(dirname "$0")/.."

BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
say()  { printf "${BOLD}==>${RESET} %s\n" "$1"; }
ok()   { printf "    ${GREEN}ok${RESET} ${DIM}%s${RESET}\n" "$1"; }
warn() { printf "    ${YELLOW}!${RESET}  %s\n" "$1"; }
die()  { printf "\n\033[31mFAILED:\033[0m %s\n\n" "$1" >&2; exit 1; }

KIND_VERSION="v0.32.0"

# --- kind -------------------------------------------------------------------
say "kind"
if command -v kind >/dev/null 2>&1; then
  ok "already installed: $(kind version | awk '{print $2}')"
else
  case "$(uname -s)" in
    Darwin)
      if command -v brew >/dev/null 2>&1; then
        brew install kind
      else
        ARCH=$([ "$(uname -m)" = "arm64" ] && echo arm64 || echo amd64)
        curl -sSLo /tmp/kind "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-darwin-${ARCH}"
        chmod +x /tmp/kind && sudo mv /tmp/kind /usr/local/bin/kind
      fi
      ;;
    Linux)
      ARCH=$([ "$(uname -m)" = "aarch64" ] && echo arm64 || echo amd64)
      curl -sSLo /tmp/kind "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-${ARCH}"
      chmod +x /tmp/kind && sudo mv /tmp/kind /usr/local/bin/kind
      ;;
    *) die "unsupported OS $(uname -s). On Windows, run this inside WSL2." ;;
  esac
  if command -v kind >/dev/null 2>&1; then
    ok "installed $(kind version | awk '{print $2}')"
  else
    warn "kind did not land on PATH — you will not be able to run a cluster."
    warn "Lab 1 does not need one; continuing."
  fi
fi

# --- kubectl ----------------------------------------------------------------
say "kubectl"
if command -v kubectl >/dev/null 2>&1; then
  ok "already installed: $(kubectl version --client 2>/dev/null | awk -F': *' '/Client Version/{print $2; exit}')"
else
  case "$(uname -s)" in
    Darwin) command -v brew >/dev/null 2>&1 && brew install kubectl || die "install kubectl: https://kubernetes.io/docs/tasks/tools/" ;;
    Linux)
      ARCH=$([ "$(uname -m)" = "aarch64" ] && echo arm64 || echo amd64)
      KV=$(curl -sSL https://dl.k8s.io/release/stable.txt)
      curl -sSLo /tmp/kubectl "https://dl.k8s.io/release/${KV}/bin/linux/${ARCH}/kubectl"
      chmod +x /tmp/kubectl && sudo mv /tmp/kubectl /usr/local/bin/kubectl
      ;;
  esac
  ok "installed"
fi

# --- docker -----------------------------------------------------------------
# A missing Docker is a WARNING, not a failure.
#
# This used to `die` here, which meant a Tier B attendee — the exact person the
# error message was reassuring — never reached the venv step below, so they had
# no rank_bm25 and no PyYAML, and Lab 1 could not run at all. The README
# promises Lab 1 needs nothing but Python. This is what makes that true.
say "docker"
DOCKER_OK=0
if docker info >/dev/null 2>&1; then
  ok "daemon reachable ($(docker version --format '{{.Server.Version}}'))"
  DOCKER_OK=1
else
  warn "Docker is not reachable — skipping cluster tooling."
  warn "That is fine: continuing so Lab 1 works, which needs only Python."
fi

# --- python venv ------------------------------------------------------------
say "python"
. scripts/lib/pick-python.sh
[ -n "$PY" ] || die "need Python 3.11-3.13 (found $(python3 -V 2>&1)). On macOS: brew install python@3.12"
ok "using $PY ($PYV)"

if [ ! -x .venv/bin/python ]; then
  "$PY" -m venv .venv
  ok "created .venv"
else
  VENV_V=$(.venv/bin/python -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  if [ "$VENV_V" != "$PYV" ]; then
    say "python (rebuilding .venv: was $VENV_V, want $PYV)"
    rm -rf .venv && "$PY" -m venv .venv
  fi
  ok ".venv present"
fi

.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt
ok "dependencies installed from requirements.txt (pinned)"

# --- env --------------------------------------------------------------------
say "env"
if [ ! -f .env ]; then
  cp .env.example .env
  ok "created .env from .env.example — add your ANTHROPIC_API_KEY before Lab 2"
else
  ok ".env present"
fi

echo
if [ "$DOCKER_OK" = 1 ]; then
  printf "${GREEN}${BOLD}setup complete.${RESET} Next: ${BOLD}make cluster${RESET}\n\n"
else
  printf "${GREEN}${BOLD}setup complete${RESET} (without cluster tooling — you are Tier B).\n\n"
  printf "  Lab 1 works right now and needs no Docker:\n\n"
  printf "    ${BOLD}make lab1 ARGS='\"why are prod inference pods repeatedly restarting?\" --environment prod --namespace ml-prod'${RESET}\n\n"
  printf "  ${DIM}Labs 2-4 need a cluster. Follow those on screen and run them later\n"
  printf "  from a machine that allows Docker. Nothing expires.${RESET}\n\n"
fi
