#!/usr/bin/env python3

import argparse
import hashlib
import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RKNN_TOOLKIT2_VERSION = "2.3.2"
DEFAULT_TARGET_PLATFORM = "rk3576"
DEFAULT_REPORT = ROOT / "output" / "rknn_conversion_report_ppocrv5.txt"

CASE_LAYOUTS = {
    "mobile_detection": {
        "variant": "mobile",
        "model": "detection",
        "source": ROOT / "PP-OCRv5_mobile_det" / "inference.onnx",
        "artifact_root": ROOT / "detection",
        "input_name": "x",
        "output_name": "fetch_name_0",
        "dynamic_input": [
            [[1, 3, 736, 736]],
            [[1, 3, 736, 1280]],
            [[1, 3, 1280, 736]],
        ],
    },
    "mobile_recognition": {
        "variant": "mobile",
        "model": "recognition",
        "source": ROOT / "PP-OCRv5_mobile_rec" / "inference.onnx",
        "artifact_root": ROOT / "recognition",
        "input_name": "x",
        "output_name": "fetch_name_0",
        "dynamic_input": [
            [[1, 3, 48, 320]],
            [[1, 3, 48, 640]],
            [[1, 3, 48, 960]],
        ],
        "op_target": {
            "exSoftmax13": "cpu",
        },
    },
    "server_detection": {
        "variant": "server",
        "model": "detection",
        "source": ROOT / "PP-OCRv5_server_det" / "inference.onnx",
        "artifact_root": ROOT / "PP-OCRv5_server_det",
        "input_name": "x",
        "output_name": "fetch_name_0",
        "dynamic_input": [
            [[1, 3, 736, 736]],
            [[1, 3, 736, 1280]],
            [[1, 3, 1280, 736]],
        ],
    },
    "server_recognition": {
        "variant": "server",
        "model": "recognition",
        "source": ROOT / "PP-OCRv5_server_rec" / "inference.onnx",
        "artifact_root": ROOT / "PP-OCRv5_server_rec",
        "input_name": "x",
        "output_name": "fetch_name_0",
        "dynamic_input": [
            [[1, 3, 48, 320]],
            [[1, 3, 48, 640]],
            [[1, 3, 48, 960]],
        ],
        "op_target": {
            "exSoftmax13": "cpu",
        },
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert unified PP-OCRv5 ONNX models to RKNN.")
    parser.add_argument(
        "--case",
        choices=["all", *CASE_LAYOUTS.keys()],
        default="all",
        help="Convert one case or all unified cases.",
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
        "--report",
        default=str(DEFAULT_REPORT),
        help="Unified conversion report path.",
    )
    return parser.parse_args()


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
            f"Install {EXPECTED_RKNN_TOOLKIT2_VERSION} before converting."
        )
    normalized = installed_version.split("+", 1)[0]
    if normalized != EXPECTED_RKNN_TOOLKIT2_VERSION:
        raise RuntimeError(
            "Unsupported rknn-toolkit2 version: "
            f"{installed_version}. Expected {EXPECTED_RKNN_TOOLKIT2_VERSION}."
        )
    return installed_version


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def format_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def artifact_path(case_name: str, target_platform: str) -> Path:
    return CASE_LAYOUTS[case_name]["artifact_root"] / "rknpu" / target_platform / "model.rknn"


def convert_case(
    case_name: str,
    *,
    target_platform: str,
    do_quantization: bool,
    verbose: bool,
) -> Path:
    from rknn.api import RKNN

    config = CASE_LAYOUTS[case_name]
    source = config["source"]
    if not source.exists():
        raise FileNotFoundError(f"Missing ONNX source for {case_name}: {source}")

    output = artifact_path(case_name, target_platform)
    output.parent.mkdir(parents=True, exist_ok=True)

    rknn = RKNN(verbose=verbose)
    try:
        print(f"[{case_name}] source={source}")
        print(f"[{case_name}] output={output}")
        print(f"[{case_name}] target_platform={target_platform}")
        print(f"[{case_name}] dynamic_input={config['dynamic_input']}")
        print(f"[{case_name}] op_target={config.get('op_target', 'n/a')}")

        ret = rknn.config(
            target_platform=target_platform,
            dynamic_input=config["dynamic_input"],
            op_target=config.get("op_target"),
        )
        if ret != 0:
            raise RuntimeError(f"{case_name}: rknn.config failed with code {ret}")

        ret = rknn.load_onnx(model=str(source))
        if ret != 0:
            raise RuntimeError(f"{case_name}: rknn.load_onnx failed with code {ret}")

        ret = rknn.build(do_quantization=do_quantization)
        if ret != 0:
            raise RuntimeError(f"{case_name}: rknn.build failed with code {ret}")

        ret = rknn.export_rknn(str(output))
        if ret != 0:
            raise RuntimeError(f"{case_name}: rknn.export_rknn failed with code {ret}")
    finally:
        rknn.release()

    return output


def run_isolated(
    case_name: str,
    *,
    target_platform: str,
    do_quantization: bool,
    verbose: bool,
    report: Path,
) -> None:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--case",
        case_name,
        "--target-platform",
        target_platform,
        "--report",
        str(report),
    ]
    if do_quantization:
        command.append("--do-quantization")
    if verbose:
        command.append("--verbose")

    temp_dir = ROOT / "output" / "tmp" / case_name
    temp_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TMPDIR"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    env["TEMP"] = str(temp_dir)
    subprocess.run(command, check=True, cwd=ROOT, env=env)


def write_report(
    outputs: dict[str, Path],
    *,
    report_path: Path,
    installed_rknn_version: str | None,
    target_platform: str,
    do_quantization: bool,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "pipeline: ppocrv5_unified",
        f"rknn-toolkit2: {installed_rknn_version or 'not installed in current environment'}",
        f"required_rknn_toolkit2: {EXPECTED_RKNN_TOOLKIT2_VERSION}",
        f"target_platform: {target_platform}",
        f"do_quantization: {do_quantization}",
        "mean_values/std_values: not set",
        "input_preprocess: external (runtime), not baked into RKNN",
        "",
    ]

    for case_name, artifact in outputs.items():
        config = CASE_LAYOUTS[case_name]
        lines.extend(
            [
                f"[{case_name}]",
                f"variant: {config['variant']}",
                f"model: {config['model']}",
                f"source: {format_path(config['source'])}",
                f"output: {format_path(artifact)}",
                f"input_name: {config['input_name']}",
                f"output_name: {config['output_name']}",
                f"dynamic_input: {config['dynamic_input']}",
                f"op_target: {config.get('op_target', 'n/a')}",
                f"sha256: {sha256sum(artifact)}",
                "",
            ]
        )

    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    report_path = Path(args.report).resolve()
    requested = list(CASE_LAYOUTS.keys()) if args.case == "all" else [args.case]
    installed_version = get_rknn_toolkit2_version()

    print(f"rknn-toolkit2: {installed_version or 'not installed'}")
    if args.case == "all":
        ensure_supported_toolkit_version()
        for case_name in requested:
            run_isolated(
                case_name,
                target_platform=args.target_platform,
                do_quantization=args.do_quantization,
                verbose=args.verbose,
                report=report_path,
            )
        outputs = {case_name: artifact_path(case_name, args.target_platform) for case_name in requested}
    else:
        ensure_supported_toolkit_version()
        artifact = convert_case(
            args.case,
            target_platform=args.target_platform,
            do_quantization=args.do_quantization,
            verbose=args.verbose,
        )
        outputs = {args.case: artifact}

    for case_name, path in outputs.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing output for {case_name}: {path}")

    write_report(
        outputs,
        report_path=report_path,
        installed_rknn_version=installed_version,
        target_platform=args.target_platform,
        do_quantization=args.do_quantization,
    )
    print(f"report={report_path}")
    for case_name, artifact in outputs.items():
        print(f"{case_name}: {artifact} sha256={sha256sum(artifact)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
