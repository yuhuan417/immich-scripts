#!/usr/bin/env python3

import argparse
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = ROOT / "assets" / "general_ocr_002.png"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "accuracy_inputs"

# A wide text-line crop taken from the bundled demo image.
REC_CROP_BOX = (98, 441, 833, 480)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare bundled accuracy_analysis inputs for PP-OCRv5 mobile.")
    parser.add_argument(
        "--image",
        default=str(DEFAULT_IMAGE),
        help="Sample image used to create accuracy analysis inputs.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory used to store generated .npy inputs.",
    )
    return parser.parse_args()


def make_detection_input(image_bgr: np.ndarray) -> np.ndarray:
    canvas_h, canvas_w = 736, 1280
    height, width = image_bgr.shape[:2]
    scale = min(canvas_w / width, canvas_h / height)
    resized_w = max(1, min(canvas_w, int(round(width * scale))))
    resized_h = max(1, min(canvas_h, int(round(height * scale))))
    resized = cv2.resize(image_bgr, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.float32)
    canvas[:resized_h, :resized_w, :] = resized.astype(np.float32)
    return np.transpose(canvas, (2, 0, 1))[None, ...]


def make_recognition_input(image_bgr: np.ndarray) -> np.ndarray:
    x1, y1, x2, y2 = REC_CROP_BOX
    crop = image_bgr[y1:y2, x1:x2, :]
    target_h, target_w = 48, 960
    scale = target_h / max(1, crop.shape[0])
    resized_w = max(1, min(target_w, int(round(crop.shape[1] * scale))))
    resized = cv2.resize(crop, (resized_w, target_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.zeros((target_h, target_w, 3), dtype=np.float32)
    canvas[:, :resized_w, :] = resized.astype(np.float32)
    canvas = canvas / 255.0
    canvas = (canvas - 0.5) / 0.5
    return np.transpose(canvas, (2, 0, 1))[None, ...]


def main() -> int:
    args = parse_args()
    image_path = Path(args.image)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise FileNotFoundError(f"Failed to read image: {image_path}")

    det_path = output_dir / "ppocrv5_mobile_det_1x3x736x1280.npy"
    rec_path = output_dir / "ppocrv5_mobile_rec_1x3x48x960.npy"

    det_input = make_detection_input(image_bgr)
    rec_input = make_recognition_input(image_bgr)

    np.save(det_path, det_input.astype(np.float32))
    np.save(rec_path, rec_input.astype(np.float32))

    print(f"detection_input: {det_path} shape={det_input.shape} dtype={det_input.dtype}")
    print(f"recognition_input: {rec_path} shape={rec_input.shape} dtype={rec_input.dtype}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
