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

MODEL_LAYOUTS = {
    "mobile_detection": {
        "model_name": "PP-OCRv5_mobile_det",
        "archive_name": "PP-OCRv5_mobile_det_infer.tar",
        "url": (
            "https://paddle-model-ecology.bj.bcebos.com/"
            "paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_mobile_det_infer.tar"
        ),
        "extract_dir": "PP-OCRv5_mobile_det_infer",
        "target_dir": ROOT / "PP-OCRv5_mobile_det",
    },
    "mobile_recognition": {
        "model_name": "PP-OCRv5_mobile_rec",
        "archive_name": "PP-OCRv5_mobile_rec_infer.tar",
        "url": (
            "https://paddle-model-ecology.bj.bcebos.com/"
            "paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_mobile_rec_infer.tar"
        ),
        "extract_dir": "PP-OCRv5_mobile_rec_infer",
        "target_dir": ROOT / "PP-OCRv5_mobile_rec",
    },
    "server_detection": {
        "model_name": "PP-OCRv5_server_det",
        "archive_name": "PP-OCRv5_server_det_infer.tar",
        "url": (
            "https://paddle-model-ecology.bj.bcebos.com/"
            "paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_server_det_infer.tar"
        ),
        "extract_dir": "PP-OCRv5_server_det_infer",
        "target_dir": ROOT / "PP-OCRv5_server_det",
    },
    "server_recognition": {
        "model_name": "PP-OCRv5_server_rec",
        "archive_name": "PP-OCRv5_server_rec_infer.tar",
        "url": (
            "https://paddle-model-ecology.bj.bcebos.com/"
            "paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_server_rec_infer.tar"
        ),
        "extract_dir": "PP-OCRv5_server_rec_infer",
        "target_dir": ROOT / "PP-OCRv5_server_rec",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download official PP-OCRv5 Paddle inference models and export ONNX for mobile/server det/rec."
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
    return parser.parse_args()


def has_paddle_inference_files(model_dir: Path) -> bool:
    return (
        model_dir.exists()
        and ((model_dir / "inference.pdmodel").exists() or (model_dir / "inference.json").exists())
        and (model_dir / "inference.pdiparams").exists()
    )


def download_file(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
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


def download_by_model_name(model_name: str, cache_root: Path, target_dir: Path) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(cache_root)
    try:
        official_models_mod = importlib.import_module("paddlex.inference.utils.official_models")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Fallback model-name download requires paddlex. "
            "Install paddlex in the export environment or use URL download."
        ) from exc

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
) -> Path:
    model_dir = source_root / extract_dir
    archive_path = download_root / archive_name

    if has_paddle_inference_files(model_dir):
        print(f"model skip: {model_dir}")
        return model_dir

    if archive_path.exists():
        return extract_archive(archive_path, source_root, extract_dir)

    try:
        download_file(url, archive_path)
        return extract_archive(archive_path, source_root, extract_dir)
    except Exception as exc:
        print(f"url download failed for {model_name}: {exc}")

    print(f"fallback to official model name: {model_name}")
    return download_by_model_name(model_name, cache_root, model_dir)


def export_onnx(model_dir: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target_onnx = target_dir / "inference.onnx"
    target_yml = target_dir / "inference.yml"

    model_filename = "inference.pdmodel"
    if not (model_dir / model_filename).exists():
        if (model_dir / "inference.json").exists():
            model_filename = "inference.json"
        else:
            raise FileNotFoundError(f"Missing inference.pdmodel or inference.json in {model_dir}")

    if target_onnx.exists():
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

    for case_name, config in MODEL_LAYOUTS.items():
        model_dir = prepare_model_dir(
            model_name=config["model_name"],
            archive_name=config["archive_name"],
            url=config["url"],
            extract_dir=config["extract_dir"],
            download_root=download_root,
            source_root=source_root,
            cache_root=cache_root,
        )
        onnx_path = export_onnx(model_dir, config["target_dir"])
        print(f"{case_name}: source={model_dir} onnx={onnx_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
