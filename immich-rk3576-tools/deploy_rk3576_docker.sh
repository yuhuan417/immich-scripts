#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMMICH_REPO="${IMMICH_REPO:-}"

COMPOSE_DIR="/root/immich"
BASE_COMPOSE="docker-compose.yml"
OVERRIDE_COMPOSE="docker-compose.rk3576-ml.yml"
ENV_FILE=".env"
IMAGE_TAG="immich-ml:rknn-rk3576-local"
MODEL_CACHE_VOLUME="immich_model-cache"

CLIP_MODEL_NAME="nllb-clip-large-siglip__v1"
FACE_MODEL_NAME="buffalo_l"
OCR_MODEL_NAME="PP-OCRv5_mobile"

CLIP_BUNDLE_PATH=""
CLIP_BUNDLE_URL=""
FACE_BUNDLE_PATH=""
FACE_BUNDLE_URL=""
OCR_BUNDLE_PATH=""
OCR_BUNDLE_URL=""
START_SERVICE=0

usage() {
  cat <<'EOF'
Usage:
  deploy_rk3576_docker.sh [options]

Options:
  --immich-repo PATH        Immich repository root containing machine-learning/Dockerfile.
                            Can also be set via IMMICH_REPO env var.
  --compose-dir PATH         Compose project directory. Default: /root/immich
  --image-tag TAG           Local Docker image tag. Default: immich-ml:rknn-rk3576-local
  --volume NAME             Docker volume used for /cache. Default: immich_model-cache
  --clip-bundle PATH        Local CLIP bundle path (.tar.gz or .part-00)
  --clip-bundle-url URL     CLIP bundle URL (.tar.gz or .part-00)
  --face-bundle PATH        Local face bundle path (.tar.gz or .part-00)
  --face-bundle-url URL     Face bundle URL (.tar.gz or .part-00)
  --ocr-bundle PATH         Local OCR bundle path (.tar.gz or .part-00)
  --ocr-bundle-url URL      OCR bundle URL (.tar.gz or .part-00)
  --start                   Run `docker compose up -d immich-machine-learning` after preparation
  -h, --help                Show this help

Examples:
  ./immich-rk3576-tools/deploy_rk3576_docker.sh \
    --immich-repo /path/to/immich \
    --clip-bundle /path/to/clip-nllb-clip-large-siglip__v1-rk3576-bundle.tar.gz.part-00 \
    --face-bundle /path/to/facial-buffalo_l-rk3576-bundle.tar.gz \
    --ocr-bundle /path/to/ocr-ppocrv5_mobile-rk3576-bundle.tar.gz

  ./immich-rk3576-tools/deploy_rk3576_docker.sh \
    --immich-repo /path/to/immich \
    --clip-bundle-url https://example.com/clip-nllb-clip-large-siglip__v1-rk3576-bundle.tar.gz.part-00 \
    --face-bundle-url https://example.com/facial-buffalo_l-rk3576-bundle.tar.gz \
    --ocr-bundle-url https://example.com/ocr-ppocrv5_mobile-rk3576-bundle.tar.gz \
    --start
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --immich-repo)
      IMMICH_REPO="$2"
      shift 2
      ;;
    --compose-dir)
      COMPOSE_DIR="$2"
      shift 2
      ;;
    --image-tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --volume)
      MODEL_CACHE_VOLUME="$2"
      shift 2
      ;;
    --clip-bundle)
      CLIP_BUNDLE_PATH="$2"
      shift 2
      ;;
    --clip-bundle-url)
      CLIP_BUNDLE_URL="$2"
      shift 2
      ;;
    --face-bundle)
      FACE_BUNDLE_PATH="$2"
      shift 2
      ;;
    --face-bundle-url)
      FACE_BUNDLE_URL="$2"
      shift 2
      ;;
    --ocr-bundle)
      OCR_BUNDLE_PATH="$2"
      shift 2
      ;;
    --ocr-bundle-url)
      OCR_BUNDLE_URL="$2"
      shift 2
      ;;
    --start)
      START_SERVICE=1
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

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd sudo
require_cmd docker
require_cmd python3
require_cmd curl

if [[ -n "${CLIP_BUNDLE_PATH}" && -n "${CLIP_BUNDLE_URL}" ]]; then
  echo "Use only one of --clip-bundle or --clip-bundle-url" >&2
  exit 1
fi
if [[ -n "${FACE_BUNDLE_PATH}" && -n "${FACE_BUNDLE_URL}" ]]; then
  echo "Use only one of --face-bundle or --face-bundle-url" >&2
  exit 1
fi
if [[ -n "${OCR_BUNDLE_PATH}" && -n "${OCR_BUNDLE_URL}" ]]; then
  echo "Use only one of --ocr-bundle or --ocr-bundle-url" >&2
  exit 1
fi

if [[ ! -d "${COMPOSE_DIR}" ]]; then
  echo "Compose directory does not exist: ${COMPOSE_DIR}" >&2
  exit 1
fi
if [[ ! -f "${COMPOSE_DIR}/${BASE_COMPOSE}" ]]; then
  echo "Compose file not found: ${COMPOSE_DIR}/${BASE_COMPOSE}" >&2
  exit 1
fi
if [[ ! -f "${COMPOSE_DIR}/${ENV_FILE}" ]]; then
  echo "Environment file not found: ${COMPOSE_DIR}/${ENV_FILE}" >&2
  exit 1
fi

if [[ -z "${IMMICH_REPO}" ]]; then
  if [[ -f "${SCRIPT_DIR}/../immich/machine-learning/Dockerfile" ]]; then
    IMMICH_REPO="$(cd "${SCRIPT_DIR}/../immich" && pwd)"
  else
    echo "Missing --immich-repo (or IMMICH_REPO env). Cannot locate machine-learning/Dockerfile." >&2
    exit 1
  fi
fi

if [[ ! -f "${IMMICH_REPO}/machine-learning/Dockerfile" ]]; then
  echo "Immich machine-learning Dockerfile not found: ${IMMICH_REPO}/machine-learning/Dockerfile" >&2
  exit 1
fi

WORKDIR="$(mktemp -d /tmp/deploy-rk3576-docker.XXXXXX)"
trap 'rm -rf "${WORKDIR}"' EXIT

assemble_local_bundle() {
  local input="$1"
  local dest="$2"

  if [[ -f "${input}" ]]; then
    if [[ "${input}" == *.part-* ]]; then
      local prefix="${input%part-*}part-"
      local parts=( "${prefix}"* )
      if [[ ! -e "${parts[0]}" ]]; then
        echo "No local parts found for ${input}" >&2
        exit 1
      fi
      cat "${parts[@]}" > "${dest}"
    else
      cp -f "${input}" "${dest}"
    fi
    return
  fi

  if compgen -G "${input}.part-*" >/dev/null 2>&1; then
    local parts=( "${input}.part-"* )
    cat "${parts[@]}" > "${dest}"
    return
  fi

  echo "Local bundle not found: ${input}" >&2
  exit 1
}

download_url_to_file() {
  local url="$1"
  local dest="$2"
  curl -L --fail --output "${dest}" "${url}"
}

assemble_remote_bundle() {
  local url="$1"
  local dest="$2"

  if [[ "${url}" == *.part-* ]]; then
    local prefix="${url%part-*}part-"
    local index=0
    local downloaded=0
    while true; do
      local part_url part_file
      part_url="${prefix}$(printf '%02d' "${index}")"
      part_file="${WORKDIR}/part-$(printf '%02d' "${index}")"
      if curl -L --fail --silent --show-error --output "${part_file}" "${part_url}"; then
        downloaded=1
        index=$((index + 1))
      else
        rm -f "${part_file}"
        break
      fi
    done
    if [[ "${downloaded}" -eq 0 ]]; then
      echo "Failed to download split bundle from ${url}" >&2
      exit 1
    fi
    cat "${WORKDIR}"/part-* > "${dest}"
    rm -f "${WORKDIR}"/part-*
  else
    download_url_to_file "${url}" "${dest}"
  fi
}

materialize_bundle() {
  local label="$1"
  local local_path="$2"
  local remote_url="$3"
  local out_name="$4"
  local dest="${WORKDIR}/${out_name}"

  if [[ -n "${local_path}" ]]; then
    echo "[deploy] Preparing ${label} bundle from local source"
    assemble_local_bundle "${local_path}" "${dest}"
    echo "${dest}"
    return
  fi

  if [[ -n "${remote_url}" ]]; then
    echo "[deploy] Downloading ${label} bundle from ${remote_url}"
    assemble_remote_bundle "${remote_url}" "${dest}"
    echo "${dest}"
    return
  fi

  echo ""
}

extract_bundle() {
  local archive="$1"
  local target_root="$2"

  case "${archive}" in
    *.tar.gz) sudo tar -xzf "${archive}" -C "${target_root}" ;;
    *.tar) sudo tar -xf "${archive}" -C "${target_root}" ;;
    *)
      echo "Unsupported archive format: ${archive}" >&2
      exit 1
      ;;
  esac
}

install_bundle() {
  local label="$1"
  local archive="$2"
  local target_dir="$3"

  if [[ -z "${archive}" ]]; then
    return
  fi

  local backup_dir="${target_dir}.bak.$(date +%Y%m%d%H%M%S)"
  echo "[deploy] Installing ${label} bundle into ${target_dir}"
  if sudo test -d "${target_dir}"; then
    sudo mkdir -p "$(dirname "${target_dir}")"
    sudo cp -a "${target_dir}" "${backup_dir}"
    echo "[deploy] Previous ${label} directory backed up to ${backup_dir}"
    sudo rm -rf "${target_dir}"
  fi

  extract_bundle "${archive}" "${MODEL_CACHE_MOUNTPOINT}"
}

echo "[deploy] Building RKNN image ${IMAGE_TAG}"
sudo docker build \
  -f "${IMMICH_REPO}/machine-learning/Dockerfile" \
  --build-arg DEVICE=rknn \
  -t "${IMAGE_TAG}" \
  "${IMMICH_REPO}/machine-learning"

echo "[deploy] Ensuring Docker volume ${MODEL_CACHE_VOLUME}"
sudo docker volume inspect "${MODEL_CACHE_VOLUME}" >/dev/null 2>&1 || sudo docker volume create "${MODEL_CACHE_VOLUME}" >/dev/null
MODEL_CACHE_MOUNTPOINT="$(sudo docker volume inspect "${MODEL_CACHE_VOLUME}" --format '{{.Mountpoint}}')"
echo "[deploy] Model cache mountpoint: ${MODEL_CACHE_MOUNTPOINT}"

CLIP_ARCHIVE="$(materialize_bundle clip "${CLIP_BUNDLE_PATH}" "${CLIP_BUNDLE_URL}" "clip-bundle.tar.gz")"
FACE_ARCHIVE="$(materialize_bundle face "${FACE_BUNDLE_PATH}" "${FACE_BUNDLE_URL}" "face-bundle.tar.gz")"
OCR_ARCHIVE="$(materialize_bundle ocr "${OCR_BUNDLE_PATH}" "${OCR_BUNDLE_URL}" "ocr-bundle.tar.gz")"

install_bundle "clip" "${CLIP_ARCHIVE}" "${MODEL_CACHE_MOUNTPOINT}/clip/${CLIP_MODEL_NAME}"
install_bundle "face" "${FACE_ARCHIVE}" "${MODEL_CACHE_MOUNTPOINT}/facial-recognition/${FACE_MODEL_NAME}"
install_bundle "ocr" "${OCR_ARCHIVE}" "${MODEL_CACHE_MOUNTPOINT}/ocr/${OCR_MODEL_NAME}"

echo "[deploy] Updating ${COMPOSE_DIR}/${ENV_FILE}"
sudo python3 - <<PY
from pathlib import Path

env_path = Path(${COMPOSE_DIR@Q}) / ${ENV_FILE@Q}
lines = env_path.read_text().splitlines()
updates = {
    "MACHINE_LEARNING_PRELOAD__CLIP__TEXTUAL": "${CLIP_MODEL_NAME}",
    "MACHINE_LEARNING_PRELOAD__CLIP__VISUAL": "${CLIP_MODEL_NAME}",
    "MACHINE_LEARNING_PRELOAD__FACIAL_RECOGNITION__DETECTION": "${FACE_MODEL_NAME}",
    "MACHINE_LEARNING_PRELOAD__FACIAL_RECOGNITION__RECOGNITION": "${FACE_MODEL_NAME}",
    "MACHINE_LEARNING_PRELOAD__OCR__DETECTION": "${OCR_MODEL_NAME}",
    "MACHINE_LEARNING_PRELOAD__OCR__RECOGNITION": "${OCR_MODEL_NAME}",
}
index = {line.split("=", 1)[0]: i for i, line in enumerate(lines) if "=" in line}
for key, value in updates.items():
    entry = f"{key}={value}"
    if key in index:
        lines[index[key]] = entry
    else:
        lines.append(entry)
env_path.write_text("\\n".join(lines) + "\\n")
PY

echo "[deploy] Writing override compose file ${COMPOSE_DIR}/${OVERRIDE_COMPOSE}"
sudo tee "${COMPOSE_DIR}/${OVERRIDE_COMPOSE}" >/dev/null <<EOF
services:
  immich-machine-learning:
    image: ${IMAGE_TAG}
    security_opt:
      - systempaths=unconfined
      - apparmor=unconfined
    devices:
      - /dev/dri:/dev/dri
EOF

cat <<EOF

[deploy] Ready.

Use this command to start or update the machine-learning service:
  cd ${COMPOSE_DIR}
  sudo docker compose -f ${BASE_COMPOSE} -f ${OVERRIDE_COMPOSE} up -d immich-machine-learning

Use this command to inspect logs:
  cd ${COMPOSE_DIR}
  sudo docker compose -f ${BASE_COMPOSE} -f ${OVERRIDE_COMPOSE} logs -f immich-machine-learning

EOF

if [[ "${START_SERVICE}" -eq 1 ]]; then
  echo "[deploy] Starting immich-machine-learning"
  cd "${COMPOSE_DIR}"
  sudo docker compose -f "${BASE_COMPOSE}" -f "${OVERRIDE_COMPOSE}" up -d immich-machine-learning
fi
