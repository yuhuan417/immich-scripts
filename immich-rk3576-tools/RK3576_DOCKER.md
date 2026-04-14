# RK3576 Docker Deployment

This document covers deploying the `immich-machine-learning` service on a fresh RK3576 board using a locally built RKNN image.

## Scope

The workflow here prepares only the machine-learning service. It assumes:

- You have this `immich-scripts` repository on the board.
- You have an `immich` source repository available (pass via `--immich-repo`).
- Your Immich deployment files live in `/root/immich`.
- Docker and Docker Compose are already installed and working.

Reference templates are also kept in this directory:

- [`docker-compose.rk3576.example.yml`](./docker-compose.rk3576.example.yml)
- [`rk3576.env.example`](./rk3576.env.example)

## What the Deployment Script Does

Use [`deploy_rk3576_docker.sh`](./deploy_rk3576_docker.sh) to:

1. Build a local RKNN machine-learning image from `<immich-repo>/machine-learning/Dockerfile`
2. Ensure the Docker model-cache volume exists
3. Optionally import verified CLIP, face, and OCR bundles into the model-cache volume
4. Automatically stitch split bundle parts when needed
5. Update `/root/immich/.env` with CLIP, face, and OCR preload settings
5. Generate a compose override file that points `immich-machine-learning` at the new local image tag and adds RKNN device access
6. Optionally start the service

The script does **not** overwrite your main `docker-compose.yml`. It writes an override file instead.

## Models

### CLIP, Facial Recognition, and OCR

In this rk3576 branch, you should treat all three model families as deployment assets derived from a verified cache:

- `clip/*`
- `facial-recognition/*`
- `ocr/*`

You can provide each bundle from:

- A local file path via `--clip-bundle`, `--face-bundle`, `--ocr-bundle`
- A download URL via `--clip-bundle-url`, `--face-bundle-url`, `--ocr-bundle-url`

Bundle formats supported by the deployment script:

- Single `*.tar.gz` archive
- Split `*.tar.gz.part-00`, `*.part-01`, ... archives

If you pass a local or remote `*.part-00`, the script will automatically concatenate all parts in order before extracting them.

## Usage

From the `immich-scripts` repository root:

```bash
chmod +x immich-rk3576-tools/deploy_rk3576_docker.sh
./immich-rk3576-tools/deploy_rk3576_docker.sh \
  --immich-repo /path/to/immich \
  --clip-bundle /path/to/clip-nllb-clip-large-siglip__v1-rk3576-bundle.tar.gz.part-00 \
  --face-bundle /path/to/facial-buffalo_l-rk3576-bundle.tar.gz \
  --ocr-bundle /path/to/ocr-ppocrv5_mobile-rk3576-bundle.tar.gz
```

Or, if the bundles are hosted somewhere reachable:

```bash
./immich-rk3576-tools/deploy_rk3576_docker.sh \
  --immich-repo /path/to/immich \
  --clip-bundle-url https://example.com/clip-nllb-clip-large-siglip__v1-rk3576-bundle.tar.gz.part-00 \
  --face-bundle-url https://example.com/facial-buffalo_l-rk3576-bundle.tar.gz \
  --ocr-bundle-url https://example.com/ocr-ppocrv5_mobile-rk3576-bundle.tar.gz
```

To build and immediately restart the service:

```bash
./immich-rk3576-tools/deploy_rk3576_docker.sh \
  --immich-repo /path/to/immich \
  --clip-bundle /path/to/clip-nllb-clip-large-siglip__v1-rk3576-bundle.tar.gz.part-00 \
  --face-bundle /path/to/facial-buffalo_l-rk3576-bundle.tar.gz \
  --ocr-bundle /path/to/ocr-ppocrv5_mobile-rk3576-bundle.tar.gz \
  --start
```

## Default Assumptions

The script defaults to:

- Compose directory: `/root/immich`
- Base compose file: `/root/immich/docker-compose.yml`
- Env file: `/root/immich/.env`
- Override file: `/root/immich/docker-compose.rk3576-ml.yml`
- Image tag: `immich-ml:rknn-rk3576-local`
- Docker volume: `immich_model-cache`

If you prefer to manage the deployment manually instead of using the script, start from the example compose and env files in this directory and then adapt paths, image tag, and preload values to your environment.

## What Gets Written

The script updates `.env` to ensure:

```text
MACHINE_LEARNING_PRELOAD__CLIP__TEXTUAL=nllb-clip-large-siglip__v1
MACHINE_LEARNING_PRELOAD__CLIP__VISUAL=nllb-clip-large-siglip__v1
MACHINE_LEARNING_PRELOAD__FACIAL_RECOGNITION__DETECTION=buffalo_l
MACHINE_LEARNING_PRELOAD__FACIAL_RECOGNITION__RECOGNITION=buffalo_l
MACHINE_LEARNING_PRELOAD__OCR__DETECTION=PP-OCRv5_mobile
MACHINE_LEARNING_PRELOAD__OCR__RECOGNITION=PP-OCRv5_mobile
```

It also writes a compose override file containing:

```yaml
services:
  immich-machine-learning:
    image: <your-local-image-tag>
    security_opt:
      - systempaths=unconfined
      - apparmor=unconfined
    devices:
      - /dev/dri:/dev/dri
```

## Start or Update the Service

After the script finishes:

```bash
cd /root/immich
sudo docker compose -f docker-compose.yml -f docker-compose.rk3576-ml.yml up -d immich-machine-learning
```

## Verification

Ping:

```bash
curl http://127.0.0.1:3003/ping
```

Logs:

```bash
cd /root/immich
sudo docker compose -f docker-compose.yml -f docker-compose.rk3576-ml.yml logs -f immich-machine-learning
```

You should see the verified RKNN models load from:

- `/cache/clip/nllb-clip-large-siglip__v1/...`
- `/cache/facial-recognition/buffalo_l/...`
- `/cache/ocr/PP-OCRv5_mobile/...`
