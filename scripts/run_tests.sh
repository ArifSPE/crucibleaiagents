#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
Usage: ./scripts/run_tests.sh [OPTIONS] [-- PYTEST_ARGS...]

Run project test suites with convenient presets.

Options:
  --api                 Run only API tests (api/tests)
  --all                 Run all tests (default)
  --file PATH           Run a specific test file (can be provided multiple times)
  -k, --keyword EXPR    Pytest -k expression
  -m, --marker EXPR     Pytest -m expression
  -q, --quiet           Quiet output
  -v, --verbose         Verbose output
  --help                Show this help message

Examples:
  ./scripts/run_tests.sh
  ./scripts/run_tests.sh --api
  ./scripts/run_tests.sh --file api/tests/test_runs.py
  ./scripts/run_tests.sh --api -k schedule
  ./scripts/run_tests.sh -- --maxfail=1 -x
EOF
}

MODE="all"
QUIET=0
VERBOSE=0
KEYWORD=""
MARKER=""
declare -a FILES=()
declare -a EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api)
      MODE="api"
      shift
      ;;
    --all)
      MODE="all"
      shift
      ;;
    --file)
      [[ $# -lt 2 ]] && { echo "Error: --file requires a path"; exit 2; }
      FILES+=("$2")
      shift 2
      ;;
    -k|--keyword)
      [[ $# -lt 2 ]] && { echo "Error: $1 requires an expression"; exit 2; }
      KEYWORD="$2"
      shift 2
      ;;
    -m|--marker)
      [[ $# -lt 2 ]] && { echo "Error: $1 requires an expression"; exit 2; }
      MARKER="$2"
      shift 2
      ;;
    -q|--quiet)
      QUIET=1
      shift
      ;;
    -v|--verbose)
      VERBOSE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --)
      shift
      EXTRA_ARGS+=("$@")
      break
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

# Prefer repo venv if present.
if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv/bin/activate"
fi

declare -a TARGETS=()
if [[ ${#FILES[@]} -gt 0 ]]; then
  TARGETS=("${FILES[@]}")
elif [[ "$MODE" == "api" ]]; then
  TARGETS=("api/tests")
else
  TARGETS=("api/tests")
fi

declare -a PYTEST_ARGS=()
if [[ $QUIET -eq 1 ]]; then
  PYTEST_ARGS+=("-q")
fi
if [[ $VERBOSE -eq 1 ]]; then
  PYTEST_ARGS+=("-v")
fi
if [[ -n "$KEYWORD" ]]; then
  PYTEST_ARGS+=("-k" "$KEYWORD")
fi
if [[ -n "$MARKER" ]]; then
  PYTEST_ARGS+=("-m" "$MARKER")
fi

PYTEST_ARGS+=("${TARGETS[@]}")
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  PYTEST_ARGS+=("${EXTRA_ARGS[@]}")
fi

echo "Running: python -m pytest ${PYTEST_ARGS[*]}"
python -m pytest "${PYTEST_ARGS[@]}"
