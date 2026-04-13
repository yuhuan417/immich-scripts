#!/usr/bin/env python3

import argparse
import hashlib
import json
import sys
from pathlib import Path

import onnx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from immich_model_exporter.exporters.onnx.models import mclip
from immich_model_exporter.exporters.onnx.models import openclip
from immich_model_exporter.exporters.rknn import export as export_rknn

MODEL_SPECS = {
    "XLM-Roberta-Large-Vit-B-16Plus": {
        "source": "mclip",
        "export_name": "M-CLIP/XLM-Roberta-Large-Vit-B-16Plus",
    },
    "XLM-Roberta-Large-Vit-B-32": {
        "source": "mclip",
        "export_name": "M-CLIP/XLM-Roberta-Large-Vit-B-32",
    },
    "XLM-Roberta-Large-Vit-L-14": {
        "source": "mclip",
        "export_name": "M-CLIP/XLM-Roberta-Large-Vit-L-14",
    },
    "XLM-Roberta-Base-ViT-B-32__laion5b_s13b_b90k": {
        "source": "openclip",
        "export_name": "xlm-roberta-base-ViT-B-32__laion5b_s13b_b90k",
    },
    "XLM-Roberta-Large-ViT-H-14__frozen_laion5b_s13b_b90k": {
        "source": "openclip",
        "export_name": "xlm-roberta-large-ViT-H-14__frozen_laion5b_s13b_b90k",
    },
    "nllb-clip-base-siglip__mrl": {
        "source": "openclip",
        "export_name": "nllb-clip-base-siglip__mrl",
    },
    "nllb-clip-base-siglip__v1": {
        "source": "openclip",
        "export_name": "nllb-clip-base-siglip__v1",
    },
    "nllb-clip-large-siglip__mrl": {
        "source": "openclip",
        "export_name": "nllb-clip-large-siglip__mrl",
    },
    "nllb-clip-large-siglip__v1": {
        "source": "openclip",
        "export_name": "nllb-clip-large-siglip__v1",
    },
}
DEFAULT_MODELS = list(MODEL_SPECS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export selected M-CLIP textual ONNX models to RKNN serially without accuracy analysis."
    )
    parser.add_argument(
        "--model",
        action="append",
        choices=DEFAULT_MODELS,
        help="Model name to convert. Repeat to select a subset. Defaults to all three models.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "models"),
        help="Root output directory for exported models.",
    )
    parser.add_argument(
        "--target-platform",
        default="rk3576",
        help="RKNN target platform.",
    )
    parser.add_argument(
        "--opset-version",
        type=int,
        default=19,
        help="ONNX opset version for textual export.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-export ONNX and RKNN artifacts even when cached files exist.",
    )
    parser.add_argument(
        "--cpu-softmax",
        action="store_true",
        help="Force all named Softmax nodes onto CPU via RKNN op_target.",
    )
    parser.add_argument(
        "--cpu-op",
        action="append",
        default=[],
        help="Additional ONNX node names to force onto CPU via RKNN op_target. Repeatable.",
    )
    parser.add_argument(
        "--report-path",
        default=str(ROOT / "output" / "selected_textual_rknn_report.json"),
        help="Path to the JSON report file.",
    )
    return parser.parse_args()


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_named_softmax_nodes(model_path: Path) -> list[str]:
    model = onnx.load(model_path.as_posix(), load_external_data=False)
    names = [node.name for node in model.graph.node if node.op_type == "Softmax" and node.name]
    return sorted(set(names))


def build_op_target(model_path: Path, cpu_softmax: bool, cpu_ops: list[str]) -> dict[str, str] | None:
    op_names = list(cpu_ops)
    if cpu_softmax:
        op_names.extend(collect_named_softmax_nodes(model_path))
    op_names = sorted(set(op_names))
    if not op_names:
        return None
    return {name: "cpu" for name in op_names}


def export_one(
    *,
    model_name: str,
    output_root: Path,
    target_platform: str,
    opset_version: int,
    cache: bool,
    cpu_softmax: bool,
    cpu_ops: list[str],
) -> dict:
    spec = MODEL_SPECS[model_name]
    export_name = spec["export_name"]
    model_root = output_root / model_name
    textual_dir = model_root / "textual"
    textual_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{model_name}] exporting textual ONNX from {export_name}")
    if spec["source"] == "mclip":
        _, textual_path = mclip.to_onnx(
            export_name,
            opset_version,
            output_dir_visual=None,
            output_dir_textual=textual_dir,
            cache=cache,
        )
    elif spec["source"] == "openclip":
        openclip_name, _, pretrained = export_name.partition("__")
        _, textual_path = openclip.to_onnx(
            openclip.OpenCLIPModelConfig(openclip_name, pretrained),
            opset_version,
            output_dir_visual=None,
            output_dir_textual=textual_dir,
            cache=cache,
        )
    else:
        raise ValueError(f"Unsupported source for {model_name}: {spec['source']}")
    assert textual_path is not None

    op_target = build_op_target(textual_path, cpu_softmax, cpu_ops)
    print(f"[{model_name}] op_target={op_target or {}}")
    print(f"[{model_name}] converting to RKNN for {target_platform}")
    export_rknn(
        model_root,
        cache=cache,
        target_platform=target_platform,
        op_target=op_target,
    )

    rknn_path = model_root / "textual" / "rknpu" / target_platform / "model.rknn"
    if not rknn_path.exists():
        raise FileNotFoundError(f"Missing RKNN artifact: {rknn_path}")

    return {
        "model_name": model_name,
        "source": spec["source"],
        "export_name": export_name,
        "onnx_path": textual_path.as_posix(),
        "rknn_path": rknn_path.as_posix(),
        "target_platform": target_platform,
        "cpu_softmax": cpu_softmax,
        "op_target": op_target or {},
        "onnx_sha256": sha256sum(textual_path),
        "rknn_sha256": sha256sum(rknn_path),
    }


def main() -> int:
    args = parse_args()
    models = args.model or DEFAULT_MODELS
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    results = []
    for model_name in models:
        results.append(
            export_one(
                model_name=model_name,
                output_root=output_root,
                target_platform=args.target_platform,
                opset_version=args.opset_version,
                cache=not args.force,
                cpu_softmax=args.cpu_softmax,
                cpu_ops=args.cpu_op,
            )
        )

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({"models": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
