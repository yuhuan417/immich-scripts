#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SOURCE_ROOT="/var/lib/docker/volumes/immich_model-cache/_data"
OUTPUT_DIR="${REPO_ROOT}/model-bundles"
TARGET_SOC="rk3576"
SPLIT_THRESHOLD_MB="1900"

usage() {
  cat <<'EOF'
Usage:
  export_verified_model_bundles.sh [options]

Options:
  --source-root PATH   Root model cache directory to export from.
                       Default: /var/lib/docker/volumes/immich_model-cache/_data
  --output-dir PATH    Directory for generated bundles.
                       Default: <repo>/model-bundles
  --target-soc SOC     Target SoC.
                       Default: rk3576
  --split-threshold-mb N
                       Split generated archives larger than N MiB.
                       Default: 1900
  -h, --help           Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-root)
      SOURCE_ROOT="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --target-soc)
      TARGET_SOC="$2"
      shift 2
      ;;
    --split-threshold-mb)
      SPLIT_THRESHOLD_MB="$2"
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

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

need_cmd sudo
need_cmd tar
need_cmd sha256sum
need_cmd split

PYTHON_BIN="${SCRIPT_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

SPLIT_BYTES=$((SPLIT_THRESHOLD_MB * 1024 * 1024))

if ! sudo test -d "${SOURCE_ROOT}"; then
  echo "Source root does not exist: ${SOURCE_ROOT}" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"
WORKDIR="$(mktemp -d /tmp/verified-model-bundles.XXXXXX)"
trap 'rm -rf "${WORKDIR}"' EXIT

copy_file() {
  local src="$1"
  local dst_root="$2"
  local rel="$3"
  local dst="${dst_root}/${rel}"

  if ! sudo test -f "${src}"; then
    echo "Missing required file: ${src}" >&2
    exit 1
  fi

  mkdir -p "$(dirname "${dst}")"
  sudo cp -a "${src}" "${dst}"
  sudo chown "$(id -u):$(id -g)" "${dst}"
}

build_bundle() {
  local name="$1"
  local stage_dir="$2"
  local archive_path="$3"

  rm -f "${archive_path}"
  rm -f "${archive_path}.part-"*
  tar -czf "${archive_path}" -C "${stage_dir}" .
  echo "[export] ${name}: ${archive_path}"
}

split_bundle_if_needed() {
  local archive_path="$1"
  local size
  size="$(stat -c %s "${archive_path}")"
  if (( size <= SPLIT_BYTES )); then
    echo "${archive_path}"
    return
  fi

  local prefix="${archive_path}.part-"
  rm -f "${prefix}"*
  split -b "${SPLIT_THRESHOLD_MB}M" -d -a 2 "${archive_path}" "${prefix}"
  rm -f "${archive_path}"
  ls "${prefix}"*
}

# CLIP bundle
CLIP_STAGE="${WORKDIR}/clip"
CLIP_ROOT="${SOURCE_ROOT}/clip/nllb-clip-large-siglip__v1"
copy_file "${CLIP_ROOT}/config.json" "${CLIP_STAGE}" "clip/nllb-clip-large-siglip__v1/config.json"
copy_file "${CLIP_ROOT}/README.md" "${CLIP_STAGE}" "clip/nllb-clip-large-siglip__v1/README.md"
copy_file "${CLIP_ROOT}/.gitattributes" "${CLIP_STAGE}" "clip/nllb-clip-large-siglip__v1/.gitattributes"
copy_file "${CLIP_ROOT}/textual/rknpu/${TARGET_SOC}/model.rknn" "${CLIP_STAGE}" "clip/nllb-clip-large-siglip__v1/textual/rknpu/${TARGET_SOC}/model.rknn"
copy_file "${CLIP_ROOT}/textual/sentencepiece.bpe.model" "${CLIP_STAGE}" "clip/nllb-clip-large-siglip__v1/textual/sentencepiece.bpe.model"
copy_file "${CLIP_ROOT}/textual/special_tokens_map.json" "${CLIP_STAGE}" "clip/nllb-clip-large-siglip__v1/textual/special_tokens_map.json"
copy_file "${CLIP_ROOT}/textual/_text_transformer_embed_positions_Constant_4_attr__value" "${CLIP_STAGE}" "clip/nllb-clip-large-siglip__v1/textual/_text_transformer_embed_positions_Constant_4_attr__value"
copy_file "${CLIP_ROOT}/textual/tokenizer_config.json" "${CLIP_STAGE}" "clip/nllb-clip-large-siglip__v1/textual/tokenizer_config.json"
copy_file "${CLIP_ROOT}/textual/tokenizer.json" "${CLIP_STAGE}" "clip/nllb-clip-large-siglip__v1/textual/tokenizer.json"
copy_file "${CLIP_ROOT}/visual/preprocess_cfg.json" "${CLIP_STAGE}" "clip/nllb-clip-large-siglip__v1/visual/preprocess_cfg.json"
copy_file "${CLIP_ROOT}/visual/rknpu/${TARGET_SOC}/model.rknn" "${CLIP_STAGE}" "clip/nllb-clip-large-siglip__v1/visual/rknpu/${TARGET_SOC}/model.rknn"

# Face bundle
FACE_STAGE="${WORKDIR}/face"
FACE_ROOT="${SOURCE_ROOT}/facial-recognition/buffalo_l"
copy_file "${FACE_ROOT}/README.md" "${FACE_STAGE}" "facial-recognition/buffalo_l/README.md"
copy_file "${FACE_ROOT}/.gitattributes" "${FACE_STAGE}" "facial-recognition/buffalo_l/.gitattributes"
copy_file "${FACE_ROOT}/detection/model.onnx" "${FACE_STAGE}" "facial-recognition/buffalo_l/detection/model.onnx"
copy_file "${FACE_ROOT}/detection/rknpu/${TARGET_SOC}/model.rknn" "${FACE_STAGE}" "facial-recognition/buffalo_l/detection/rknpu/${TARGET_SOC}/model.rknn"
copy_file "${FACE_ROOT}/recognition/model.onnx" "${FACE_STAGE}" "facial-recognition/buffalo_l/recognition/model.onnx"
copy_file "${FACE_ROOT}/recognition/rknpu/${TARGET_SOC}/model.rknn" "${FACE_STAGE}" "facial-recognition/buffalo_l/recognition/rknpu/${TARGET_SOC}/model.rknn"

# OCR bundle
OCR_STAGE="${WORKDIR}/ocr"
OCR_ROOT="${SOURCE_ROOT}/ocr/PP-OCRv5_mobile"
copy_file "${OCR_ROOT}/detection/rknpu/${TARGET_SOC}/model.rknn" "${OCR_STAGE}" "ocr/PP-OCRv5_mobile/detection/rknpu/${TARGET_SOC}/model.rknn"
copy_file "${OCR_ROOT}/recognition/rknpu/${TARGET_SOC}/model.rknn" "${OCR_STAGE}" "ocr/PP-OCRv5_mobile/recognition/rknpu/${TARGET_SOC}/model.rknn"

RAPIDOCR_DICT="$("${PYTHON_BIN}" - <<'PY'
from pathlib import Path
import importlib.util

spec = importlib.util.find_spec("rapidocr")
if spec is None or spec.origin is None:
    print("")
    raise SystemExit(0)

pkg_dir = Path(spec.origin).resolve().parent
dict_path = pkg_dir / "models" / "ppocrv5_dict.txt"
print(dict_path if dict_path.is_file() else "")
PY
)"
if [[ -n "${RAPIDOCR_DICT}" ]]; then
  copy_file "${RAPIDOCR_DICT}" "${OCR_STAGE}" "ocr/PP-OCRv5_mobile/recognition/ppocrv5_dict.txt"
fi

CLIP_ARCHIVE="${OUTPUT_DIR}/clip-nllb-clip-large-siglip__v1-${TARGET_SOC}-bundle.tar.gz"
FACE_ARCHIVE="${OUTPUT_DIR}/facial-buffalo_l-${TARGET_SOC}-bundle.tar.gz"
OCR_ARCHIVE="${OUTPUT_DIR}/ocr-ppocrv5_mobile-${TARGET_SOC}-bundle.tar.gz"

build_bundle "clip" "${CLIP_STAGE}" "${CLIP_ARCHIVE}"
build_bundle "face" "${FACE_STAGE}" "${FACE_ARCHIVE}"
build_bundle "ocr" "${OCR_STAGE}" "${OCR_ARCHIVE}"

readarray -t CLIP_OUTPUTS < <(split_bundle_if_needed "${CLIP_ARCHIVE}")
readarray -t FACE_OUTPUTS < <(split_bundle_if_needed "${FACE_ARCHIVE}")
readarray -t OCR_OUTPUTS < <(split_bundle_if_needed "${OCR_ARCHIVE}")

(
  cd "${OUTPUT_DIR}"
  SHA_INPUTS=(
    "${CLIP_OUTPUTS[@]##*/}"
    "${FACE_OUTPUTS[@]##*/}"
    "${OCR_OUTPUTS[@]##*/}"
  )
  sha256sum "${SHA_INPUTS[@]}" > SHA256SUMS.txt
)

cat <<EOF

[export] Done.
Output directory: ${OUTPUT_DIR}

Generated files:
EOF

for file in "${CLIP_OUTPUTS[@]}" "${FACE_OUTPUTS[@]}" "${OCR_OUTPUTS[@]}"; do
  printf '  %s\n' "${file}"
done

cat <<EOF
  ${OUTPUT_DIR}/SHA256SUMS.txt
EOF
