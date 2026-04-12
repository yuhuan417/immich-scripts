#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPORT_VENV="${ROOT_DIR}/.venv-export"
CONVERT_VENV="${ROOT_DIR}/.venv-rknn"
TARGET_PLATFORM="rk3576"
RKNN_WHEEL=""
PYTHON_BIN=""
FORCE_DOWNLOAD=0
FORCE_EXPORT=0

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
  tools/build_ppocrv5_mobile_rknn.sh [options]

Options:
  --target-platform NAME   RKNN target platform. Default: rk3576
  --export-venv PATH       Export virtualenv path. Default: <repo>/.venv-export
  --convert-venv PATH      RKNN virtualenv path. Default: <repo>/.venv-rknn
  --python BIN             Python executable used to create both virtualenvs.
  --rknn-wheel PATH        Install rknn-toolkit2 from a local wheel.
  --force-download         Re-download official Paddle inference archives.
  --force-export           Re-export ONNX from the raw Paddle inference models.
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
    --rknn-wheel)
      RKNN_WHEEL="$2"
      shift 2
      ;;
    --force-download)
      FORCE_DOWNLOAD=1
      shift
      ;;
    --force-export)
      FORCE_EXPORT=1
      shift
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

EXPORT_SETUP_CMD=("${ROOT_DIR}/tools/setup_mobile_export_env.sh" --venv "${EXPORT_VENV}")
CONVERT_SETUP_CMD=("${ROOT_DIR}/tools/setup_convert_env.sh" --venv "${CONVERT_VENV}")
if [[ -n "${PYTHON_BIN}" ]]; then
  EXPORT_SETUP_CMD+=(--python "${PYTHON_BIN}")
  CONVERT_SETUP_CMD+=(--python "${PYTHON_BIN}")
fi
if [[ -n "${RKNN_WHEEL}" ]]; then
  CONVERT_SETUP_CMD+=(--rknn-wheel "${RKNN_WHEEL}")
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

EXPORT_CMD=("${EXPORT_PYTHON}" "${ROOT_DIR}/tools/download_and_export_ppocrv5_mobile.py")
if [[ "${FORCE_DOWNLOAD}" -eq 1 ]]; then
  EXPORT_CMD+=(--force-download)
fi
if [[ "${FORCE_EXPORT}" -eq 1 ]]; then
  EXPORT_CMD+=(--force-export)
fi

"${EXPORT_CMD[@]}"
"${CONVERT_PYTHON}" "${ROOT_DIR}/tools/prepare_ppocrv5_mobile_accuracy_inputs.py"

DET_INPUT="${ROOT_DIR}/output/accuracy_inputs/ppocrv5_mobile_det_1x3x736x1280.npy"
REC_INPUT="${ROOT_DIR}/output/accuracy_inputs/ppocrv5_mobile_rec_1x3x48x960.npy"

"${CONVERT_PYTHON}" "${ROOT_DIR}/tools/convert_ppocrv5_rknn.py" \
  --variant mobile \
  --model detection \
  --target-platform "${TARGET_PLATFORM}" \
  --accuracy-analysis-input "${DET_INPUT}" \
  --accuracy-analysis-output-dir "${ROOT_DIR}/output/accuracy_analysis/mobile/detection/${TARGET_PLATFORM}"

"${CONVERT_PYTHON}" "${ROOT_DIR}/tools/convert_ppocrv5_rknn.py" \
  --variant mobile \
  --model recognition \
  --target-platform "${TARGET_PLATFORM}" \
  --accuracy-analysis-input "${REC_INPUT}" \
  --accuracy-analysis-output-dir "${ROOT_DIR}/output/accuracy_analysis/mobile/recognition/${TARGET_PLATFORM}"

"${CONVERT_PYTHON}" "${ROOT_DIR}/tools/run_ppocrv5_accuracy_suite.py" \
  --target-platform "${TARGET_PLATFORM}" \
  --cases mobile_detection mobile_recognition \
  --summary-only

echo
echo "Pipeline complete."
echo "Artifacts:"
echo "  ${ROOT_DIR}/PP-OCRv5_mobile_det/inference.onnx"
echo "  ${ROOT_DIR}/PP-OCRv5_mobile_rec/inference.onnx"
echo "  ${ROOT_DIR}/detection/rknpu/${TARGET_PLATFORM}/model.rknn"
echo "  ${ROOT_DIR}/recognition/rknpu/${TARGET_PLATFORM}/model.rknn"
echo "Accuracy summary:"
echo "  ${ROOT_DIR}/output/accuracy_analysis/ppocrv5_accuracy_comparison_${TARGET_PLATFORM}.md"
