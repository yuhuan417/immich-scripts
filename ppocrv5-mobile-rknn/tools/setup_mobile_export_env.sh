#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv-export"
PYTHON_BIN=""

usage() {
  cat <<'EOF'
Usage:
  tools/setup_mobile_export_env.sh [--venv PATH] [--python PYTHON_BIN]

Options:
  --venv PATH         Virtualenv location. Default: <repo>/.venv-export
  --python BIN        Python executable used to create the virtualenv.
                      Default: python3.11, fallback to python3
  -h, --help          Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --venv)
      VENV_DIR="$2"
      shift 2
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${PYTHON_BIN}" ]]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="python3.11"
  elif [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

PYTHON_VERSION="$("${PYTHON_BIN}" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
if [[ "${PYTHON_VERSION}" != "3.11" ]]; then
  echo "Python 3.11 is required for the pinned export dependencies, got ${PYTHON_VERSION} from ${PYTHON_BIN}" >&2
  exit 1
fi

create_virtualenv() {
  if "${PYTHON_BIN}" -m venv "${VENV_DIR}" >/dev/null 2>&1; then
    return 0
  fi

  echo "python -m venv failed, trying virtualenv fallback..." >&2
  if ! "${PYTHON_BIN}" -m virtualenv --version >/dev/null 2>&1; then
    "${PYTHON_BIN}" -m pip install --user --break-system-packages virtualenv
  fi
  "${PYTHON_BIN}" -m virtualenv "${VENV_DIR}"
}

create_virtualenv

VENV_PYTHON="${VENV_DIR}/bin/python"

"${VENV_PYTHON}" -m pip install --upgrade "pip<26" "setuptools<81" wheel
"${VENV_PYTHON}" -m pip install -r "${ROOT_DIR}/tools/requirements-mobile-export.txt"

"${VENV_PYTHON}" - <<'PY'
import importlib.metadata as metadata
import platform
import sys

required = {
    "paddlepaddle": "3.0.0",
    "paddle2onnx": "2.0.2rc1",
    "numpy": "1.24.4",
    "onnx": "1.17.0",
}

print(f"Python: {sys.version.split()[0]}")
print(f"Platform: {platform.platform()}")
for name, expected in required.items():
    installed = metadata.version(name)
    print(f"{name}: {installed}")
    if installed.split("+", 1)[0] != expected:
        raise SystemExit(f"{name} version mismatch: expected {expected}, got {installed}")
PY

echo
echo "Mobile export environment ready."
echo "Export command:"
echo "  ${VENV_PYTHON} ${ROOT_DIR}/tools/download_and_export_ppocrv5_mobile.py"
