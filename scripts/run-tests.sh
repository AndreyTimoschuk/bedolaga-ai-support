#!/usr/bin/env bash
# One-shot: bootstrap stack → pytest → print results → remove test containers.
set -euo pipefail

# Resolve symlinks so ./test.sh → scripts/run-tests.sh still finds the repo root
_src="${BASH_SOURCE[0]}"
while [[ -L "$_src" ]]; do
  _dir="$(cd "$(dirname "$_src")" && pwd)"
  _link="$(readlink "$_src")"
  if [[ "$_link" == /* ]]; then
    _src="$_link"
  else
    _src="$_dir/$_link"
  fi
done
ROOT="$(cd "$(dirname "$_src")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.test}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-support-e2e}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file "$ENV_FILE")

KEEP_STACK="${KEEP_STACK:-0}"
MARKERS="${MARKERS:-contract or e2e}"
PYTEST_ARGS="${PYTEST_ARGS:-}"

CONTRACT_EXIT=0
E2E_EXIT=0
OVERALL_EXIT=0
CLEANED=0

cleanup() {
  if [[ "$CLEANED" -eq 1 ]]; then
    return
  fi
  CLEANED=1
  if [[ "$KEEP_STACK" == "1" ]]; then
    echo
    echo "==> KEEP_STACK=1 — containers left running ($COMPOSE_PROJECT_NAME)"
    return
  fi
  echo
  echo "==> Tearing down test stack ($COMPOSE_PROJECT_NAME)"
  "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  echo "Containers removed."
}

trap cleanup EXIT

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  echo "Copy .env.test.example → .env.test and fill tokens + TEST_USER_CHAT_ID"
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "==> Creating .venv"
  python3 -m venv .venv
fi
if ! .venv/bin/python -c "import pytest, httpx, redis, asyncpg" 2>/dev/null; then
  echo "==> Installing requirements-dev.txt"
  .venv/bin/pip install -q -r requirements-dev.txt
fi

# Ensure JPEG fixture exists for photo contract tests
if [[ ! -s tests/fixtures/pixel.jpg ]]; then
  echo "==> Fetching tests/fixtures/pixel.jpg"
  mkdir -p tests/fixtures
  docker run --rm -v "$ROOT/tests/fixtures:/out" curlimages/curl:latest \
    -fsSL -o /out/pixel.jpg https://httpbin.org/image/jpeg \
    || echo "WARNING: could not fetch pixel.jpg — photo contract may fail"
fi

echo "==> Bootstrap"
./scripts/e2e-bootstrap.sh

echo
echo "==> pytest -m contract"
set +e
.venv/bin/pytest tests/ -m contract -q --tb=line $PYTEST_ARGS
CONTRACT_EXIT=$?
set -e

echo
echo "==> pytest -m e2e"
set +e
.venv/bin/pytest tests/ -m e2e -q --tb=line $PYTEST_ARGS
E2E_EXIT=$?
set -e

if [[ "$CONTRACT_EXIT" -ne 0 || "$E2E_EXIT" -ne 0 ]]; then
  OVERALL_EXIT=1
fi

echo
echo "========================================"
echo " Results"
echo "========================================"
if [[ "$CONTRACT_EXIT" -eq 0 ]]; then
  echo "  contract: PASS"
else
  echo "  contract: FAIL (exit $CONTRACT_EXIT)"
fi
if [[ "$E2E_EXIT" -eq 0 ]]; then
  echo "  e2e:      PASS (skipped cases = missing /start on user bot is OK)"
else
  echo "  e2e:      FAIL (exit $E2E_EXIT)"
fi
echo "========================================"
if [[ "$OVERALL_EXIT" -eq 0 ]]; then
  echo "ALL GREEN"
else
  echo "FAILED"
fi

exit "$OVERALL_EXIT"
