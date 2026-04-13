#!/usr/bin/env python3

import argparse
import json
import shutil
import subprocess
import uuid
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEXTS = [
    "a photo of a cat",
    "一只正在睡觉的猫",
    "an astronaut riding a horse",
    "晚霞下的海边城市",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare textual ONNX and RKNN outputs on a remote rk3576 board.")
    parser.add_argument("--model-root", required=True, help="Model root containing textual/model.onnx and tokenizer files.")
    parser.add_argument("--target-platform", default="rk3576", help="RKNN target platform directory name.")
    parser.add_argument(
        "--runtime-mode",
        choices=["ssh-rknnlite", "host-remote"],
        default="ssh-rknnlite",
        help="Use RKNNLite on the board over SSH, or use host-side RKNN Toolkit remote runtime.",
    )
    parser.add_argument("--host", default="192.168.1.202", help="SSH host for the rk3576 board.")
    parser.add_argument(
        "--device-id",
        default="192.168.1.202:5555",
        help="Remote device id passed to RKNN.init_runtime() when --runtime-mode host-remote is used.",
    )
    parser.add_argument("--remote-python", default="python3", help="Python interpreter on the remote board.")
    parser.add_argument("--remote-tmp-base", default="/tmp", help="Base temporary directory on the remote board.")
    parser.add_argument(
        "--text",
        action="append",
        help="Text sample to test. Repeatable. Defaults to a built-in multilingual sample set.",
    )
    parser.add_argument(
        "--text-file",
        help="Optional UTF-8 text file with one query per line.",
    )
    parser.add_argument(
        "--report-path",
        help="Optional JSON report path. Defaults to <model-root>/textual/rknpu/<target>/compare.json.",
    )
    parser.add_argument(
        "--print-full-report",
        action="store_true",
        help="Print the full JSON report including per-query results.",
    )
    return parser.parse_args()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a_flat = a.reshape(-1).astype(np.float64)
    b_flat = b.reshape(-1).astype(np.float64)
    denom = np.linalg.norm(a_flat) * np.linalg.norm(b_flat)
    if denom == 0:
        return 0.0
    return float(np.dot(a_flat, b_flat) / denom)


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def ssh_command(host: str, remote_command: list[str]) -> list[str]:
    return ["ssh", "-F", "/dev/null", host, *remote_command]


def scp_to(host: str, sources: list[Path], destination: str) -> list[str]:
    return ["scp", "-F", "/dev/null", *[str(path) for path in sources], f"{host}:{destination}"]


def scp_from(host: str, source: str, destination: Path) -> list[str]:
    return ["scp", "-F", "/dev/null", f"{host}:{source}", str(destination)]


def summarize_metric(values: list[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min": float(arr.min()),
        "mean": float(arr.mean()),
        "max": float(arr.max()),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
    }


def load_texts(args: argparse.Namespace) -> list[str]:
    if args.text and args.text_file:
        raise ValueError("Use either --text or --text-file, not both.")
    if args.text_file:
        lines = Path(args.text_file).read_text(encoding="utf-8").splitlines()
        texts = [line.strip() for line in lines if line.strip()]
        if not texts:
            raise ValueError(f"No non-empty texts found in {args.text_file}")
        return texts
    return args.text or DEFAULT_TEXTS


def encode_for_model(tokenizer: AutoTokenizer, text: str, input_names: list[str]) -> dict[str, np.ndarray]:
    encoded = tokenizer(
        text,
        return_tensors="np",
        padding="max_length",
        truncation=True,
        max_length=77,
    )
    supported = set(input_names)
    if supported == {"text"}:
        return {"text": encoded["input_ids"].astype(np.int32)}
    if supported == {"input_ids", "attention_mask"}:
        return {
            "input_ids": encoded["input_ids"].astype(np.int32),
            "attention_mask": encoded["attention_mask"].astype(np.int32),
        }
    raise RuntimeError(f"Unsupported ONNX inputs: {input_names}")


def run_host_remote_rknn(model_path: Path, inputs: list[np.ndarray], target_platform: str, device_id: str) -> list[np.ndarray]:
    from rknn.api import RKNN

    rknn = RKNN(verbose=False)
    try:
        ret = rknn.load_rknn(model_path.as_posix())
        if ret != 0:
            raise RuntimeError(f"load_rknn failed: {ret}")
        ret = rknn.init_runtime(target=target_platform, device_id=device_id)
        if ret != 0:
            raise RuntimeError(f"init_runtime failed: {ret}")
        outputs = rknn.inference(inputs=inputs)
        return outputs
    finally:
        rknn.release()


def main() -> int:
    args = parse_args()
    model_root = Path(args.model_root).resolve()
    textual_dir = model_root / "textual"
    onnx_path = textual_dir / "model.onnx"
    rknn_path = textual_dir / "rknpu" / args.target_platform / "model.rknn"
    tokenizer_dir = textual_dir

    if args.report_path:
        report_path = Path(args.report_path).resolve()
    else:
        report_path = textual_dir / "rknpu" / args.target_platform / "compare.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_dir)
    session = ort.InferenceSession(onnx_path.as_posix(), providers=["CPUExecutionProvider"])
    input_names = [item.name for item in session.get_inputs()]
    encode_for_model(tokenizer, DEFAULT_TEXTS[0], input_names)

    texts = load_texts(args)
    local_tmp = ROOT / "output" / "tmp" / f"compare_{model_root.name}"
    local_tmp.mkdir(parents=True, exist_ok=True)
    remote_dir = f"{args.remote_tmp_base.rstrip('/')}/ml_models_textual_compare_{uuid.uuid4().hex}"
    remote_helper = ROOT / "tools" / "run_multi_input_rknn_lite_dataset.py"

    results = []
    try:
        if args.runtime_mode == "ssh-rknnlite":
            run_command(ssh_command(args.host, ["mkdir", "-p", remote_dir]))
            batched_inputs = {name: [] for name in input_names}
            encoded_inputs = []
            for text in texts:
                sample = encode_for_model(tokenizer, text, input_names)
                encoded_inputs.append(sample)
                for name in input_names:
                    batched_inputs[name].append(sample[name])

            local_input_paths = []
            for name in input_names:
                path = local_tmp / f"{name}.npy"
                np.save(path, np.concatenate(batched_inputs[name], axis=0))
                local_input_paths.append(path)
            run_command(scp_to(args.host, [rknn_path, remote_helper, *local_input_paths], remote_dir))
            remote_output = f"{remote_dir}/outputs.npz"
            local_rknn_output = local_tmp / "outputs.npz"
            remote_cmd = [
                args.remote_python,
                f"{remote_dir}/{remote_helper.name}",
                "--model",
                f"{remote_dir}/{rknn_path.name}",
            ]
            for name in input_names:
                remote_cmd.extend(["--input", f"{remote_dir}/{name}.npy"])
            remote_cmd.extend(["--output", remote_output])
            run_command(
                ssh_command(
                    args.host,
                    remote_cmd,
                )
            )
            run_command(scp_from(args.host, remote_output, local_rknn_output))
            rknn_dataset = np.load(local_rknn_output)["output_0"]
        else:
            encoded_inputs = None

        for idx, text in enumerate(texts):
            if encoded_inputs is None:
                ort_inputs = encode_for_model(tokenizer, text, input_names)
            else:
                ort_inputs = encoded_inputs[idx]
            onnx_outputs = session.run(None, ort_inputs)
            onnx_embedding = onnx_outputs[0]
            if args.runtime_mode == "host-remote":
                rknn_embedding = run_host_remote_rknn(
                    rknn_path,
                    [ort_inputs[name] for name in input_names],
                    args.target_platform,
                    args.device_id,
                )[0]
            else:
                rknn_embedding = rknn_dataset[idx : idx + 1]

            diff = np.abs(onnx_embedding.astype(np.float64) - rknn_embedding.astype(np.float64))
            results.append(
                {
                    "text": text,
                    "onnx_shape": list(onnx_embedding.shape),
                    "rknn_shape": list(rknn_embedding.shape),
                    "max_abs_diff": float(diff.max()),
                    "mean_abs_diff": float(diff.mean()),
                    "cosine_similarity": cosine_similarity(onnx_embedding, rknn_embedding),
                }
            )
            if (idx + 1) % 100 == 0 or idx + 1 == len(texts):
                print(f"compared={idx + 1}/{len(texts)}")

        summary = {
            "model_root": model_root.as_posix(),
            "onnx_path": onnx_path.as_posix(),
            "rknn_path": rknn_path.as_posix(),
            "host": args.host,
            "num_queries": len(results),
            "results": results,
            "max_abs_diff": max(item["max_abs_diff"] for item in results),
            "mean_abs_diff": float(np.mean([item["mean_abs_diff"] for item in results])),
            "min_cosine_similarity": min(item["cosine_similarity"] for item in results),
            "max_abs_diff_stats": summarize_metric([item["max_abs_diff"] for item in results]),
            "mean_abs_diff_stats": summarize_metric([item["mean_abs_diff"] for item in results]),
            "cosine_similarity_stats": summarize_metric([item["cosine_similarity"] for item in results]),
        }
        report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"report={report_path}")
        if args.print_full_report:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            compact = dict(summary)
            compact.pop("results", None)
            print(json.dumps(compact, indent=2, ensure_ascii=False))
    finally:
        if args.runtime_mode == "ssh-rknnlite":
            subprocess.run(ssh_command(args.host, ["rm", "-rf", remote_dir]), check=False)
        shutil.rmtree(local_tmp, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
