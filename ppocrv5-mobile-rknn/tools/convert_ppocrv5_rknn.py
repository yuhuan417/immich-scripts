#!/usr/bin/env python3

import argparse
import hashlib
import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_PLATFORM = "rk3576"
DEFAULT_DO_QUANTIZATION = False
EXPECTED_RKNN_TOOLKIT2_VERSION = "2.3.2"
DEFAULT_VARIANT = "mobile"

COMMON_MODELS = {
    "detection": {
        "input_name": "x",
        "output_name": "fetch_name_0",
        "dtype": "float32",
        "layout": "NCHW",
        "color_order": "BGR",
        "dynamic_input": [
            [[1, 3, 736, 736]],
            [[1, 3, 736, 1280]],
            [[1, 3, 1280, 736]],
        ],
    },
    "recognition": {
        "input_name": "x",
        "output_name": "fetch_name_0",
        "output_last_dim": 18385,
        "dtype": "float32",
        "layout": "NCHW",
        "color_order": "BGR",
        "op_target": {
            "exSoftmax13": "cpu",
        },
        "dynamic_input": [
            [[1, 3, 48, 320]],
            [[1, 3, 48, 640]],
            [[1, 3, 48, 960]],
        ],
    },
}

VARIANT_LAYOUTS = {
    "mobile": {
        "report_path": ROOT / "output" / "rknn_conversion_report.txt",
        "models": {
            "detection": {
                "source_dir": "PP-OCRv5_mobile_det",
                "artifact_dir": "detection",
            },
            "recognition": {
                "source_dir": "PP-OCRv5_mobile_rec",
                "artifact_dir": "recognition",
            },
        },
    },
    "server": {
        "report_path": ROOT / "output" / "rknn_conversion_report_server.txt",
        "models": {
            "detection": {
                "source_dir": "PP-OCRv5_server_det",
                "artifact_dir": "PP-OCRv5_server_det",
            },
            "recognition": {
                "source_dir": "PP-OCRv5_server_rec",
                "artifact_dir": "PP-OCRv5_server_rec",
            },
        },
    },
}


def model_config(model_name: str, variant: str) -> dict:
    config = dict(COMMON_MODELS[model_name])
    layout = VARIANT_LAYOUTS[variant]["models"][model_name]
    config["source"] = ROOT / layout["source_dir"] / "inference.onnx"
    config["artifact_dir"] = ROOT / layout["artifact_dir"]
    return config


def report_path_for_variant(variant: str) -> Path:
    return VARIANT_LAYOUTS[variant]["report_path"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert PP-OCRv5 ONNX models to RKNN.")
    parser.add_argument(
        "--model",
        choices=["all", *COMMON_MODELS.keys()],
        default="all",
        help="Convert a single model or both models.",
    )
    parser.add_argument(
        "--variant",
        choices=sorted(VARIANT_LAYOUTS.keys()),
        default=DEFAULT_VARIANT,
        help="Choose mobile or server ONNX sources and artifact locations.",
    )
    parser.add_argument(
        "--target-platform",
        default=DEFAULT_TARGET_PLATFORM,
        help="RKNN target platform and output directory name.",
    )
    parser.add_argument(
        "--do-quantization",
        action="store_true",
        help="Enable PTQ when building RKNN. Default keeps do_quantization=False.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable RKNN verbose logging.",
    )
    parser.add_argument(
        "--accuracy-analysis-input",
        action="append",
        default=[],
        help=(
            "Input path for RKNN accuracy_analysis. Repeat for multi-input models. "
            "Only supported when converting a single model."
        ),
    )
    parser.add_argument(
        "--accuracy-analysis-output-dir",
        help="Output directory for RKNN accuracy_analysis snapshots.",
    )
    parser.add_argument(
        "--accuracy-analysis-target",
        help="Optional target for RKNN accuracy_analysis, for example rk3576.",
    )
    parser.add_argument(
        "--device-id",
        help="Optional device_id used by RKNN accuracy_analysis.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only write the report using existing artifacts.",
    )
    return parser.parse_args()


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_rknn_toolkit2_version() -> str | None:
    try:
        return version("rknn-toolkit2")
    except PackageNotFoundError:
        return None


def ensure_supported_toolkit_version() -> str:
    installed_version = get_rknn_toolkit2_version()
    if installed_version is None:
        raise RuntimeError(
            "rknn-toolkit2 is not installed. "
            f"Run tools/setup_convert_env.sh or install {EXPECTED_RKNN_TOOLKIT2_VERSION} before converting."
        )

    normalized_version = installed_version.split("+", 1)[0]
    if normalized_version != EXPECTED_RKNN_TOOLKIT2_VERSION:
        raise RuntimeError(
            "Unsupported rknn-toolkit2 version: "
            f"{installed_version}. Expected {EXPECTED_RKNN_TOOLKIT2_VERSION}."
        )

    return installed_version


def create_rknn(*, verbose: bool):
    try:
        from rknn.api import RKNN
    except ImportError as exc:
        raise RuntimeError(
            "Failed to import rknn.api. "
            f"Run tools/setup_convert_env.sh or install rknn-toolkit2 {EXPECTED_RKNN_TOOLKIT2_VERSION}."
        ) from exc

    return RKNN(verbose=verbose)


def artifact_path(model_name: str, variant: str, target_platform: str) -> Path:
    return model_config(model_name, variant)["artifact_dir"] / "rknpu" / target_platform / "model.rknn"


def default_accuracy_output_dir(model_name: str, variant: str, target_platform: str) -> Path:
    return ROOT / "output" / "accuracy_analysis" / variant / model_name / target_platform


def run_accuracy_analysis(
    rknn,
    *,
    model_name: str,
    variant: str,
    target_platform: str,
    accuracy_inputs: list[str],
    accuracy_output_dir: str | None,
    accuracy_target: str | None,
    device_id: str | None,
) -> Path:
    output_dir = (
        Path(accuracy_output_dir)
        if accuracy_output_dir is not None
        else default_accuracy_output_dir(model_name, variant, target_platform)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[{model_name}] accuracy_analysis_inputs: {accuracy_inputs}")
    print(f"[{model_name}] accuracy_analysis_output_dir: {output_dir}")
    print(f"[{model_name}] accuracy_analysis_target: {accuracy_target or 'simulator'}")
    ret = rknn.accuracy_analysis(
        inputs=accuracy_inputs,
        output_dir=str(output_dir),
        target=accuracy_target,
        device_id=device_id,
    )
    if ret != 0:
        raise RuntimeError(f"{model_name}: rknn.accuracy_analysis failed with code {ret}")
    return output_dir


def convert(
    model_name: str,
    *,
    variant: str,
    target_platform: str,
    do_quantization: bool,
    verbose: bool,
    accuracy_inputs: list[str] | None = None,
    accuracy_output_dir: str | None = None,
    accuracy_target: str | None = None,
    device_id: str | None = None,
) -> tuple[Path, Path | None]:
    config = model_config(model_name, variant)
    source = config["source"]
    output = artifact_path(model_name, variant, target_platform)
    output.parent.mkdir(parents=True, exist_ok=True)

    rknn = create_rknn(verbose=verbose)
    try:
        print(f"[{model_name}] variant: {variant}")
        print(f"[{model_name}] source: {source}")
        print(f"[{model_name}] output: {output}")
        print(f"[{model_name}] target_platform: {target_platform}")
        print(f"[{model_name}] input_name: {config['input_name']}")
        print(f"[{model_name}] output_name: {config['output_name']}")
        print(f"[{model_name}] dynamic_input: {config['dynamic_input']}")

        ret = rknn.config(
            target_platform=target_platform,
            dynamic_input=config["dynamic_input"],
            op_target=config.get("op_target"),
        )
        if ret != 0:
            raise RuntimeError(f"{model_name}: rknn.config failed with code {ret}")

        ret = rknn.load_onnx(model=str(source))
        if ret != 0:
            raise RuntimeError(f"{model_name}: rknn.load_onnx failed with code {ret}")

        ret = rknn.build(do_quantization=do_quantization)
        if ret != 0:
            raise RuntimeError(f"{model_name}: rknn.build failed with code {ret}")

        accuracy_dir = None
        if accuracy_inputs:
            accuracy_dir = run_accuracy_analysis(
                rknn,
                model_name=model_name,
                variant=variant,
                target_platform=target_platform,
                accuracy_inputs=accuracy_inputs,
                accuracy_output_dir=accuracy_output_dir,
                accuracy_target=accuracy_target,
                device_id=device_id,
            )

        ret = rknn.export_rknn(str(output))
        if ret != 0:
            raise RuntimeError(f"{model_name}: rknn.export_rknn failed with code {ret}")

        return output, accuracy_dir
    finally:
        rknn.release()


def write_report(
    outputs: dict[str, Path],
    *,
    variant: str,
    target_platform: str,
    do_quantization: bool,
    accuracy_dirs: dict[str, Path | None] | None = None,
) -> Path:
    report_path = report_path_for_variant(variant)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    installed_version = get_rknn_toolkit2_version() or "not installed in current environment"

    lines = [
        f"variant: {variant}",
        f"rknn-toolkit2: {installed_version}",
        f"required_rknn_toolkit2: {EXPECTED_RKNN_TOOLKIT2_VERSION}",
        f"target_platform: {target_platform}",
        f"do_quantization: {do_quantization}",
        "mean_values/std_values: not set",
        "input_preprocess: external (Immich), not baked into RKNN",
        "",
    ]
    for model_name, artifact in outputs.items():
        config = model_config(model_name, variant)
        accuracy_dir = accuracy_dirs.get(model_name) if accuracy_dirs else None
        lines.extend(
            [
                f"[{model_name}]",
                f"source: {config['source'].relative_to(ROOT)}",
                f"output: {artifact.relative_to(ROOT)}",
                f"input_name: {config['input_name']}",
                f"output_name: {config['output_name']}",
                f"dtype: {config['dtype']}",
                f"layout: {config['layout']}",
                f"color_order: {config['color_order']}",
                f"dynamic_input: {config['dynamic_input']}",
                f"op_target: {config.get('op_target', 'n/a')}",
                (
                    f"output_last_dim: {config['output_last_dim']}"
                    if "output_last_dim" in config
                    else "output_last_dim: n/a"
                ),
                f"sha256: {sha256sum(artifact)}",
                (
                    f"accuracy_analysis_output_dir: {accuracy_dir.relative_to(ROOT)}"
                    if accuracy_dir is not None
                    else "accuracy_analysis_output_dir: n/a"
                ),
                "",
            ]
        )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def collect_outputs(
    model_names: list[str], *, variant: str, target_platform: str
) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    for model_name in model_names:
        artifact = artifact_path(model_name, variant, target_platform)
        if not artifact.exists():
            raise FileNotFoundError(f"Missing artifact for {model_name}: {artifact}")
        outputs[model_name] = artifact
    return outputs


def run_isolated(
    model_name: str,
    *,
    variant: str,
    target_platform: str,
    do_quantization: bool,
    verbose: bool,
) -> None:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--model",
        model_name,
        "--variant",
        variant,
        "--target-platform",
        target_platform,
    ]
    if do_quantization:
        command.append("--do-quantization")
    if verbose:
        command.append("--verbose")
    temp_dir = ROOT / "output" / "tmp" / model_name
    temp_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TMPDIR"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    env["TEMP"] = str(temp_dir)
    subprocess.run(command, check=True, cwd=ROOT, env=env)


def main() -> int:
    args = parse_args()
    requested = list(COMMON_MODELS) if args.model == "all" else [args.model]
    installed_version = get_rknn_toolkit2_version()
    accuracy_inputs = args.accuracy_analysis_input

    if accuracy_inputs and args.model == "all":
        raise ValueError("--accuracy-analysis-input only supports --model detection or --model recognition.")

    print(f"rknn-toolkit2: {installed_version or 'not installed'}")
    print(f"variant: {args.variant}")
    if args.report_only:
        outputs = collect_outputs(
            requested,
            variant=args.variant,
            target_platform=args.target_platform,
        )
        accuracy_dirs: dict[str, Path | None] = {}
    elif args.model == "all":
        ensure_supported_toolkit_version()
        for model_name in requested:
            run_isolated(
                model_name,
                variant=args.variant,
                target_platform=args.target_platform,
                do_quantization=args.do_quantization,
                verbose=args.verbose,
            )
        outputs = collect_outputs(
            requested,
            variant=args.variant,
            target_platform=args.target_platform,
        )
        accuracy_dirs = {}
    else:
        ensure_supported_toolkit_version()
        artifact, accuracy_dir = convert(
                args.model,
                variant=args.variant,
                target_platform=args.target_platform,
                do_quantization=args.do_quantization,
                verbose=args.verbose,
                accuracy_inputs=accuracy_inputs,
                accuracy_output_dir=args.accuracy_analysis_output_dir,
                accuracy_target=args.accuracy_analysis_target,
                device_id=args.device_id,
            )
        outputs = {args.model: artifact}
        accuracy_dirs = {args.model: accuracy_dir}

    report_path = write_report(
        outputs,
        variant=args.variant,
        target_platform=args.target_platform,
        do_quantization=args.do_quantization,
        accuracy_dirs=accuracy_dirs,
    )
    print(f"report: {report_path}")
    for model_name, artifact in outputs.items():
        print(f"{model_name}: {artifact} sha256={sha256sum(artifact)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
