#!/usr/bin/env python3

import argparse
from pathlib import Path

import numpy as np
from rknnlite.api import RKNNLite


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RKNNLite inference with multiple .npy inputs.")
    parser.add_argument("--model", required=True, help="Path to the RKNN model.")
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="Path to an input .npy tensor. Repeat in the exact RKNN input order.",
    )
    parser.add_argument("--output", required=True, help="Path to the output .npz file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_path = Path(args.model)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rknn = RKNNLite()
    ret = rknn.load_rknn(str(model_path))
    if ret != 0:
        raise RuntimeError(f"load_rknn failed: {ret}")

    ret = rknn.init_runtime()
    if ret != 0:
        raise RuntimeError(f"init_runtime failed: {ret}")

    try:
        inputs = [np.load(Path(path)) for path in args.input]
        outputs = rknn.inference(inputs=inputs)
        payload = {f"output_{idx}": value for idx, value in enumerate(outputs)}
        np.savez(output_path, **payload)
        print(f"model={model_path}")
        for idx, tensor in enumerate(inputs):
            print(f"input_{idx}: shape={tensor.shape} dtype={tensor.dtype}")
        for idx, value in enumerate(outputs):
            print(f"output_{idx}: shape={value.shape} dtype={value.dtype}")
        print(f"saved={output_path}")
    finally:
        rknn.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
