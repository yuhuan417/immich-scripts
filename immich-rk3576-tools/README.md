# Immich RK3576 Tools

这套脚本用于把 RK3576 相关的机器学习部署辅助能力从 `immich` 仓库独立出来，统一放在 `immich-scripts`。

## 包含内容

- `deploy_rk3576_docker.sh`: 在目标机上构建 RKNN 机器学习镜像、导入模型 bundle、写 compose override 并可直接启动服务。
- `export_verified_model_bundles.sh`: 从现有 `immich_model-cache` 卷导出已验证的 CLIP/Face/OCR bundle。
- `prepare.sh` / `run.sh`: 非 Docker 方式调试 `immich/machine-learning` 的 RKNN 环境与启动脚本（需要指定 machine-learning 目录）。
- `RK3576_DOCKER.md`: 详细部署说明。
- `docker-compose.rk3576.example.yml` / `rk3576.env.example`: 参考模板。

## 前置条件

- 有一份 `immich` 源码目录（用于构建 `machine-learning/Dockerfile`）。
- 部署目录（默认 `/root/immich`）里已有 `docker-compose.yml` 和 `.env`。
- 目标机已安装 Docker / Docker Compose。

## 最短使用路径

### 1. 导出模型 bundle（可选，若你已有 bundle 可跳过）

```bash
cd immich-scripts
./immich-rk3576-tools/export_verified_model_bundles.sh \
  --source-root /var/lib/docker/volumes/immich_model-cache/_data \
  --output-dir ./model-bundles \
  --target-soc rk3576
```

### 2. 部署/更新 RK3576 machine-learning（推荐）

```bash
cd immich-scripts
./immich-rk3576-tools/deploy_rk3576_docker.sh \
  --immich-repo /path/to/immich \
  --compose-dir /root/immich \
  --clip-bundle /path/to/clip-...tar.gz.part-00 \
  --face-bundle /path/to/facial-...tar.gz \
  --ocr-bundle /path/to/ocr-...tar.gz \
  --start
```

说明：

- `--clip/face/ocr-bundle` 也可替换为 `--*-bundle-url`。
- bundle 支持单文件 `tar.gz`，也支持分片 `part-00/01/...` 自动拼接。

### 3. 非 Docker 调试（仅开发时）

```bash
cd immich-scripts
./immich-rk3576-tools/prepare.sh --project-root /path/to/immich/machine-learning
./immich-rk3576-tools/run.sh --project-root /path/to/immich/machine-learning
```

## 常用文档

- 详细部署说明：[`RK3576_DOCKER.md`](./RK3576_DOCKER.md)
