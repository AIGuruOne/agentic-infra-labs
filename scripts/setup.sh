#!/usr/bin/env bash
# setup.sh — installs and verifies everything the labs need. Idempotent:
# running it twice is a no-op the second time.

set -euo pipefail
cd "$(dirname "$0")/.."

BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'; GREEN=$'\033[32m'
say()  { printf "${BOLD}==>${RESET} %s\n" "$1"; }
ok()   { printf "    ${GREEN}ok${RESET} ${DIM}%s${RESET}\n" "$1"; }
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
  command -v kind >/dev/null 2>&1 || die "kind install did not land on PATH"
  ok "installed $(kind version | awk '{print $2}')"
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
say "docker"
docker info >/dev/null 2>&1 || die "Docker daemon is not reachable. Start Docker Desktop, then re-run.
       If Docker is not permitted on this machine, that is fine — you are Tier B.
       Run ./scripts/doctor.sh to confirm, follow the session on screen, and run
       the labs later. Nothing expires."
ok "daemon reachable ($(docker version --format '{{.Server.Version}}'))"

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
printf "${GREEN}${BOLD}setup complete.${RESET} Next: ${BOLD}make cluster${RESET}\n\n"
