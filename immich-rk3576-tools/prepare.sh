#!/usr/bin/env bash
set -euo pipefail

# RKNN 开发环境准备脚本
# 基于 Dockerfile 的 prod-rknn 和 builder-rknn 部分

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${IMMICH_ML_DIR:-}"

usage() {
  cat <<'EOF'
Usage:
  prepare.sh [--project-root PATH]

Options:
  --project-root PATH   Immich machine-learning directory.
                        Can also be set via IMMICH_ML_DIR env var.
  -h, --help            Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root)
      PROJECT_ROOT="$2"
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

if [[ -z "${PROJECT_ROOT}" ]]; then
  if [[ -f "${SCRIPT_DIR}/pyproject.toml" && -d "${SCRIPT_DIR}/immich_ml" ]]; then
    PROJECT_ROOT="${SCRIPT_DIR}"
  elif [[ -f "${PWD}/pyproject.toml" && -d "${PWD}/immich_ml" ]]; then
    PROJECT_ROOT="${PWD}"
  else
    echo "[prepare] 错误: 无法定位 machine-learning 目录，请传 --project-root" >&2
    exit 1
  fi
fi

PROJECT_ROOT="$(cd "${PROJECT_ROOT}" && pwd)"

# RKNN 版本配置
RKNN_TOOLKIT_VERSION="v2.3.2"

# 下载目录
DOWNLOAD_DIR="$PROJECT_ROOT/.rknn_deps"
mkdir -p "$DOWNLOAD_DIR"

echo "[prepare] 准备 RKNN 开发环境..."

# 1. 检查 Python 版本
if ! command -v python3.11 &> /dev/null; then
    echo "[prepare] 错误: 未找到 python3.11" >&2
    exit 1
fi

PYTHON_VERSION=$(python3.11 --version | awk '{print $2}')
echo "[prepare] Python 版本: $PYTHON_VERSION"

# 2. 创建 Python 虚拟环境
VENV_DIR="$PROJECT_ROOT/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
    echo "[prepare] 创建 Python 虚拟环境..."
    python3.11 -m venv --python=python3.11 "$VENV_DIR"
    echo "[prepare] 虚拟环境已创建: $VENV_DIR"
else
    echo "[prepare] 虚拟环境已存在: $VENV_DIR"
fi

# 激活虚拟环境并设置环境变量
source "$VENV_DIR/bin/activate"
export VIRTUAL_ENV="$VENV_DIR"
export PATH="$VENV_DIR/bin:$PATH"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1

echo "[prepare] 虚拟环境已激活: $VIRTUAL_ENV"

# 防止产生 core dump 文件
ulimit -c 0
echo "[prepare] 已禁用 core dump 生成"

# 3. 检查是否为 ARM64 架构
ARCH=$(uname -m)
if [[ "$ARCH" != "aarch64" ]]; then
    echo "[prepare] 警告: 当前架构为 $ARCH，RKNN 运行时库仅支持 aarch64" >&2
    echo "[prepare] 如果在非 ARM64 平台上运行，可能需要交叉编译或使用模拟器" >&2
fi

# 4. 下载 RKNN 运行时库
RKNN_LIB_URL="https://github.com/airockchip/rknn-toolkit2/raw/refs/tags/${RKNN_TOOLKIT_VERSION}/rknpu2/runtime/Linux/librknn_api/aarch64/librknnrt.so"
RKNN_HEADER_URL="https://github.com/airockchip/rknn-toolkit2/raw/refs/tags/${RKNN_TOOLKIT_VERSION}/rknpu2/runtime/Linux/librknn_api/include/rknn_api.h"

RKNN_LIB_FILE="$DOWNLOAD_DIR/librknnrt.so"
RKNN_HEADER_FILE="$DOWNLOAD_DIR/rknn_api.h"

if [[ ! -f "$RKNN_LIB_FILE" ]]; then
    echo "[prepare] 下载 RKNN 运行时库..."
    curl -L -o "$RKNN_LIB_FILE" "$RKNN_LIB_URL"
    echo "[prepare] RKNN 库已下载到 $RKNN_LIB_FILE"
else
    echo "[prepare] RKNN 库已存在: $RKNN_LIB_FILE"
fi

if [[ ! -f "$RKNN_HEADER_FILE" ]]; then
    echo "[prepare] 下载 RKNN 头文件..."
    curl -L -o "$RKNN_HEADER_FILE" "$RKNN_HEADER_URL"
    echo "[prepare] RKNN 头文件已下载到 $RKNN_HEADER_FILE"
else
    echo "[prepare] RKNN 头文件已存在: $RKNN_HEADER_FILE"
fi

# 5. 检查是否已安装 uv
if ! command -v uv &> /dev/null; then
    echo "[prepare] 安装 uv 包管理器..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    echo "[prepare] uv 已安装"
else
    echo "[prepare] uv 已安装: $(uv --version)"
fi

# 6. 安装 Python 依赖
echo "[prepare] 安装 Python 依赖 (rknn extra)..."
cd "$PROJECT_ROOT"
uv sync --extra rknn

# 7. 编译 RKNN 原生模块
echo "[prepare] 编译 RKNN 原生模块..."
cd "$PROJECT_ROOT/immich_ml/sessions/rknn/native"

RKNN_HEADER="$RKNN_HEADER_FILE"
RKNN_LIBRARY="$RKNN_LIB_FILE"
RKNN_OUTPUT_DIR="$PROJECT_ROOT/immich_ml/sessions/rknn"

export RKNN_HEADER RKNN_LIBRARY RKNN_OUTPUT_DIR

if ! command -v g++ &> /dev/null; then
    echo "[prepare] 错误: 未找到 g++ 编译器" >&2
    echo "[prepare] 请安装: sudo apt-get install g++ libc6-dev" >&2
    exit 1
fi

if ! python3 -m pybind11 --includes &> /dev/null; then
    echo "[prepare] pybind11 未正确安装，请检查依赖安装" >&2
    exit 1
fi

./build-cross.sh

# 8. 设置环境变量
ENV_FILE="$PROJECT_ROOT/.env.rknn"
cat > "$ENV_FILE" << EOF
# RKNN 环境变量
DEVICE=rknn
MACHINE_LEARNING_MODEL_ARENA=false
PYTHONPATH=$PROJECT_ROOT
RKNN_LIBRARY_PATH=$RKNN_LIB_FILE
EOF

echo "[prepare] 环境变量已写入 $ENV_FILE"
echo ""
echo "[prepare] RKNN 开发环境准备完成!"
echo "[prepare] 使用 'source .env.rknn' 加载环境变量"
echo "[prepare] 使用 './run.sh' 启动服务"
