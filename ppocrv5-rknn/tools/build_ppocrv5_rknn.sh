#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPORT_VENV="${ROOT_DIR}/.venv-export"
CONVERT_VENV="${ROOT_DIR}/.venv-rknn"
TARGET_PLATFORM="rk3576"
PYTHON_BIN=""

venv_ready() {
  local venv_python="$1"
  shift
  if [[ ! -x "${venv_python}" ]]; then
    return 1
  fi
  "${venv_python}" - "$@" <<'PY'
import importlib.metadata as metadata
import sys

args = sys.argv[1:]
if len(args) % 2 != 0:
    raise SystemExit(2)

for name, expected in zip(args[::2], args[1::2]):
    try:
        installed = metadata.version(name)
    except metadata.PackageNotFoundError:
        raise SystemExit(1)
    if installed.split("+", 1)[0] != expected:
        raise SystemExit(1)
raise SystemExit(0)
PY
}

usage() {
  cat <<'EOF'
Usage:
  tools/build_ppocrv5_rknn.sh [options]

Options:
  --target-platform NAME   RKNN target platform. Default: rk3576
  --export-venv PATH       Export virtualenv path. Default: <repo>/.venv-export
  --convert-venv PATH      RKNN virtualenv path. Default: <repo>/.venv-rknn
  --python BIN             Python executable used to create both virtualenvs.
  -h, --help               Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-platform)
      TARGET_PLATFORM="$2"
      shift 2
      ;;
    --export-venv)
      EXPORT_VENV="$2"
      shift 2
      ;;
    --convert-venv)
      CONVERT_VENV="$2"
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

EXPORT_SETUP_CMD=("${ROOT_DIR}/tools/setup_export_env.sh" --venv "${EXPORT_VENV}")
CONVERT_SETUP_CMD=("${ROOT_DIR}/tools/setup_convert_env.sh" --venv "${CONVERT_VENV}")
if [[ -n "${PYTHON_BIN}" ]]; then
  EXPORT_SETUP_CMD+=(--python "${PYTHON_BIN}")
  CONVERT_SETUP_CMD+=(--python "${PYTHON_BIN}")
fi

if venv_ready \
  "${EXPORT_VENV}/bin/python" \
  paddlepaddle 3.0.0 \
  paddle2onnx 2.0.2rc1 \
  numpy 1.24.4 \
  onnx 1.17.0; then
  echo "export env ready: ${EXPORT_VENV}"
else
  "${EXPORT_SETUP_CMD[@]}"
fi

if venv_ready \
  "${CONVERT_VENV}/bin/python" \
  rknn-toolkit2 2.3.2 \
  numpy 1.24.4 \
  onnx 1.17.0 \
  onnxruntime 1.23.2; then
  echo "convert env ready: ${CONVERT_VENV}"
else
  "${CONVERT_SETUP_CMD[@]}"
fi

EXPORT_PYTHON="${EXPORT_VENV}/bin/python"
CONVERT_PYTHON="${CONVERT_VENV}/bin/python"

"${EXPORT_PYTHON}" "${ROOT_DIR}/tools/download_and_export_ppocrv5.py"
"${CONVERT_PYTHON}" "${ROOT_DIR}/tools/convert_ppocrv5_rknn.py" --target-platform "${TARGET_PLATFORM}"

echo
echo "Pipeline complete."
echo "ONNX artifacts:"
echo "  ${ROOT_DIR}/PP-OCRv5_mobile_det/inference.onnx"
echo "  ${ROOT_DIR}/PP-OCRv5_mobile_rec/inference.onnx"
echo "  ${ROOT_DIR}/PP-OCRv5_server_det/inference.onnx"
echo "  ${ROOT_DIR}/PP-OCRv5_server_rec/inference.onnx"
echo "RKNN artifacts:"
echo "  ${ROOT_DIR}/detection/rknpu/${TARGET_PLATFORM}/model.rknn"
echo "  ${ROOT_DIR}/recognition/rknpu/${TARGET_PLATFORM}/model.rknn"
echo "  ${ROOT_DIR}/PP-OCRv5_server_det/rknpu/${TARGET_PLATFORM}/model.rknn"
echo "  ${ROOT_DIR}/PP-OCRv5_server_rec/rknpu/${TARGET_PLATFORM}/model.rknn"
echo "Report:"
echo "  ${ROOT_DIR}/output/rknn_conversion_report_ppocrv5.txt"
