#!/usr/bin/env python3

import argparse
from pathlib import Path

import numpy as np
from rknnlite.api import RKNNLite


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RKNNLite inference for a stacked dataset of multiple inputs.")
    parser.add_argument("--model", required=True, help="Path to the RKNN model.")
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="Path to an input .npy tensor with batch dimension first. Repeat in exact model input order.",
    )
    parser.add_argument("--output", required=True, help="Path to the output .npz file.")
    parser.add_argument("--progress-every", type=int, default=100, help="Print progress every N samples.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_path = Path(args.model)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    dataset_inputs = [np.load(Path(path)) for path in args.input]
    num_samples = dataset_inputs[0].shape[0]
    for tensor in dataset_inputs[1:]:
        if tensor.shape[0] != num_samples:
            raise ValueError("All input tensors must share the same first dimension.")

    rknn = RKNNLite()
    ret = rknn.load_rknn(str(model_path))
    if ret != 0:
        raise RuntimeError(f"load_rknn failed: {ret}")

    ret = rknn.init_runtime()
    if ret != 0:
        raise RuntimeError(f"init_runtime failed: {ret}")

    try:
        outputs_acc: list[list[np.ndarray]] = []
        for idx in range(num_samples):
            sample_inputs = [tensor[idx : idx + 1] for tensor in dataset_inputs]
            sample_outputs = rknn.inference(inputs=sample_inputs)
            if not outputs_acc:
                outputs_acc = [[] for _ in sample_outputs]
            for out_idx, value in enumerate(sample_outputs):
                outputs_acc[out_idx].append(value)
            if (idx + 1) % args.progress_every == 0 or idx + 1 == num_samples:
                print(f"processed={idx + 1}/{num_samples}")

        payload = {
            f"output_{idx}": np.concatenate(chunks, axis=0)
            for idx, chunks in enumerate(outputs_acc)
        }
        np.savez(output_path, **payload)
        print(f"model={model_path}")
        print(f"num_samples={num_samples}")
        for idx, tensor in enumerate(dataset_inputs):
            print(f"input_{idx}: shape={tensor.shape} dtype={tensor.dtype}")
        for key, value in payload.items():
            print(f"{key}: shape={value.shape} dtype={value.dtype}")
        print(f"saved={output_path}")
    finally:
        rknn.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
