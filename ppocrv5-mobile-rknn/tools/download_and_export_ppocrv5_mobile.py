#!/usr/bin/env python3

import argparse
import importlib
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ONNX_OPSET_VERSION = "14"

MODELS = {
    "detection": {
        "model_name": "PP-OCRv5_mobile_det",
        "archive_name": "PP-OCRv5_mobile_det_infer.tar",
        "url": (
            "https://paddle-model-ecology.bj.bcebos.com/"
            "paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_mobile_det_infer.tar"
        ),
        "extract_dir": "PP-OCRv5_mobile_det_infer",
        "target_dir": ROOT / "PP-OCRv5_mobile_det",
    },
    "recognition": {
        "model_name": "PP-OCRv5_mobile_rec",
        "archive_name": "PP-OCRv5_mobile_rec_infer.tar",
        "url": (
            "https://paddle-model-ecology.bj.bcebos.com/"
            "paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_mobile_rec_infer.tar"
        ),
        "extract_dir": "PP-OCRv5_mobile_rec_infer",
        "target_dir": ROOT / "PP-OCRv5_mobile_rec",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download official PP-OCRv5 mobile Paddle inference models and export ONNX."
    )
    parser.add_argument(
        "--cache-root",
        default=str(ROOT / "artifacts" / "paddlex_cache"),
        help="Directory used by the official model-name downloader fallback.",
    )
    parser.add_argument(
        "--download-root",
        default=str(ROOT / "artifacts" / "downloads"),
        help="Directory used to store downloaded tar archives.",
    )
    parser.add_argument(
        "--source-root",
        default=str(ROOT / "artifacts" / "paddle_inference"),
        help="Directory used to extract raw Paddle inference models.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download archives even if they already exist.",
    )
    parser.add_argument(
        "--force-export",
        action="store_true",
        help="Re-export ONNX even if target inference.onnx already exists.",
    )
    return parser.parse_args()


def has_paddle_inference_files(model_dir: Path) -> bool:
    return (
        model_dir.exists()
        and ((model_dir / "inference.pdmodel").exists() or (model_dir / "inference.json").exists())
        and (model_dir / "inference.pdiparams").exists()
    )


def download_file(url: str, output_path: Path, *, force: bool) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not force:
        print(f"download skip: {output_path}")
        return
    print(f"download: {url}")
    urllib.request.urlretrieve(url, output_path)
    print(f"saved: {output_path}")


def extract_archive(archive_path: Path, source_root: Path, extract_dir: str) -> Path:
    model_dir = source_root / extract_dir
    if has_paddle_inference_files(model_dir):
        print(f"extract skip: {model_dir}")
        return model_dir

    source_root.mkdir(parents=True, exist_ok=True)
    print(f"extract: {archive_path} -> {source_root}")
    with tarfile.open(archive_path) as archive:
        archive.extractall(source_root)
    if not model_dir.exists():
        raise FileNotFoundError(f"Expected extracted directory not found: {model_dir}")
    return model_dir


def download_by_model_name(model_name: str, cache_root: Path, target_dir: Path, *, force: bool) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_model_dir = cache_root / "official_models" / model_name
    if force:
        shutil.rmtree(cache_model_dir, ignore_errors=True)
        shutil.rmtree(target_dir, ignore_errors=True)

    os.environ["PADDLE_PDX_CACHE_HOME"] = str(cache_root)
    official_models_mod = importlib.import_module("paddlex.inference.utils.official_models")
    official_models = official_models_mod.official_models
    downloaded_dir = Path(official_models[model_name])
    if not has_paddle_inference_files(downloaded_dir):
        raise FileNotFoundError(f"Official model download did not produce inference files: {downloaded_dir}")

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(downloaded_dir, target_dir, dirs_exist_ok=True)
    return target_dir


def prepare_model_dir(
    *,
    model_name: str,
    archive_name: str,
    url: str,
    extract_dir: str,
    download_root: Path,
    source_root: Path,
    cache_root: Path,
    force_download: bool,
) -> Path:
    model_dir = source_root / extract_dir
    archive_path = download_root / archive_name

    if has_paddle_inference_files(model_dir) and not force_download:
        print(f"model skip: {model_dir}")
        return model_dir

    # Prefer local artifacts first.
    if archive_path.exists() and not force_download:
        return extract_archive(archive_path, source_root, extract_dir)

    # Then explicit URL download.
    try:
        download_file(url, archive_path, force=force_download)
        return extract_archive(archive_path, source_root, extract_dir)
    except Exception as exc:
        print(f"url download failed for {model_name}: {exc}")

    # Finally, fallback to the official model-name downloader.
    print(f"fallback to official model name: {model_name}")
    return download_by_model_name(model_name, cache_root, model_dir, force=force_download)


def export_onnx(model_dir: Path, target_dir: Path, *, force: bool) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target_onnx = target_dir / "inference.onnx"
    target_yml = target_dir / "inference.yml"
    model_filename = "inference.pdmodel"
    if not (model_dir / model_filename).exists():
        if (model_dir / "inference.json").exists():
            model_filename = "inference.json"
        else:
            raise FileNotFoundError(f"Missing inference.pdmodel or inference.json in {model_dir}")
    if target_onnx.exists() and not force:
        print(f"export skip: {target_onnx}")
    else:
        command = [
            sys.executable,
            "-m",
            "paddle2onnx.command",
            "--model_dir",
            str(model_dir),
            "--model_filename",
            model_filename,
            "--params_filename",
            "inference.pdiparams",
            "--save_file",
            str(target_onnx),
            "--opset_version",
            ONNX_OPSET_VERSION,
            "--enable_onnx_checker",
            "True",
            "--optimize_tool",
            "onnxoptimizer",
        ]
        print(f"export: {' '.join(command)}")
        subprocess.run(command, check=True)
    source_yml = model_dir / "inference.yml"
    if source_yml.exists():
        shutil.copy2(source_yml, target_yml)
    return target_onnx


def main() -> int:
    args = parse_args()
    download_root = Path(args.download_root)
    source_root = Path(args.source_root)
    cache_root = Path(args.cache_root)

    for key, config in MODELS.items():
        model_dir = prepare_model_dir(
            model_name=config["model_name"],
            archive_name=config["archive_name"],
            url=config["url"],
            extract_dir=config["extract_dir"],
            download_root=download_root,
            source_root=source_root,
            cache_root=cache_root,
            force_download=args.force_download,
        )
        onnx_path = export_onnx(model_dir, config["target_dir"], force=args.force_export)
        print(f"{key}: source={model_dir} onnx={onnx_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
