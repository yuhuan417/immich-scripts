#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONVERTER = ROOT / "tools" / "convert_ppocrv5_rknn.py"
OUTPUT_ROOT = ROOT / "output" / "accuracy_analysis"
LOG_ROOT = ROOT / "output" / "logs" / "accuracy_suite"
TARGET_PLATFORM = "rk3576"

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
ROW_RE = re.compile(
    rf"^\[(?P<op>[^\]]+)\]\s+"
    rf"(?P<name>.*?)\s+"
    rf"(?P<entire_cos>{NUMBER})\s+\|\s+"
    rf"(?P<entire_euc>{NUMBER})\s+"
    rf"(?P<single_cos>{NUMBER})\s+\|\s+"
    rf"(?P<single_euc>{NUMBER})\s*$"
)


CASES = [
    {
        "variant": "mobile",
        "model": "detection",
        "accuracy_input": ROOT / "output" / "accuracy_inputs" / "ppocrv5_mobile_det_1x3x736x1280.npy",
    },
    {
        "variant": "mobile",
        "model": "recognition",
        "accuracy_input": ROOT / "output" / "accuracy_inputs" / "ppocrv5_mobile_rec_1x3x48x960.npy",
    },
    {
        "variant": "server",
        "model": "detection",
        "accuracy_input": ROOT / "output" / "accuracy_inputs" / "ppocrv5_mobile_det_1x3x736x1280.npy",
    },
    {
        "variant": "server",
        "model": "recognition",
        "accuracy_input": ROOT / "output" / "accuracy_inputs" / "ppocrv5_mobile_rec_1x3x48x960.npy",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run PP-OCRv5 RKNN conversion and accuracy analysis serially for all four models."
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=[case_key(case) for case in CASES],
        help="Only run the selected cases.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Skip execution and only summarize existing accuracy analysis outputs.",
    )
    parser.add_argument(
        "--target-platform",
        default=TARGET_PLATFORM,
        help="RKNN target platform.",
    )
    parser.add_argument(
        "--do-quantization",
        action="store_true",
        help="Enable PTQ when building RKNN. Default keeps do_quantization=False.",
    )
    parser.add_argument(
        "--accuracy-analysis-target",
        help="Optional target for RKNN accuracy_analysis, for example rk3576.",
    )
    parser.add_argument(
        "--device-id",
        help="Optional device_id used by RKNN accuracy_analysis.",
    )
    return parser.parse_args()


def case_key(case: dict) -> str:
    return f"{case['variant']}_{case['model']}"


def accuracy_dir(case: dict, target_platform: str) -> Path:
    return OUTPUT_ROOT / case["variant"] / case["model"] / target_platform


def log_path(case: dict, target_platform: str) -> Path:
    return LOG_ROOT / f"{case_key(case)}_{target_platform}.log"


def tmp_dir(case: dict, target_platform: str) -> Path:
    return ROOT / "output" / "tmp" / f"{case_key(case)}_{target_platform}"


def parse_error_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = ROW_RE.match(line)
        if not match:
            continue
        row = match.groupdict()
        row["entire_cos"] = float(row["entire_cos"])
        row["entire_euc"] = float(row["entire_euc"])
        row["single_cos"] = float(row["single_cos"])
        row["single_euc"] = float(row["single_euc"])
        rows.append(row)
    if not rows:
        raise RuntimeError(f"No layer rows parsed from {path}")
    return rows


def pick_final_output(rows: list[dict]) -> dict:
    for row in rows:
        if row["name"] == "fetch_name_0":
            return row
    return rows[-1]


def build_summary(case: dict, target_platform: str) -> dict:
    err_path = accuracy_dir(case, target_platform) / "error_analysis.txt"
    rows = parse_error_rows(err_path)
    final_row = pick_final_output(rows)
    worst_entire_cos = min(rows, key=lambda row: row["entire_cos"])
    worst_entire_euc = max(rows, key=lambda row: row["entire_euc"])
    worst_single_euc = max(rows, key=lambda row: row["single_euc"])
    avg_entire_cos = sum(row["entire_cos"] for row in rows) / len(rows)
    avg_single_cos = sum(row["single_cos"] for row in rows) / len(rows)

    log_lines = log_path(case, target_platform).read_text(encoding="utf-8", errors="ignore").splitlines()
    error_lines = [line for line in log_lines if line.startswith("E RKNN:") or line.startswith("\x1b[1;31mE")]

    return {
        "case": case_key(case),
        "variant": case["variant"],
        "model": case["model"],
        "target_platform": target_platform,
        "layer_count": len(rows),
        "final_output": final_row,
        "worst_entire_cos": worst_entire_cos,
        "worst_entire_euc": worst_entire_euc,
        "worst_single_euc": worst_single_euc,
        "average_entire_cos": avg_entire_cos,
        "average_single_cos": avg_single_cos,
        "error_analysis": str(err_path.relative_to(ROOT)),
        "log_path": str(log_path(case, target_platform).relative_to(ROOT)),
        "build_error_lines": error_lines,
    }


def write_comparison_report(summaries: list[dict], *, target_platform: str, do_quantization: bool) -> tuple[Path, Path]:
    json_path = OUTPUT_ROOT / f"ppocrv5_accuracy_comparison_{target_platform}.json"
    md_path = OUTPUT_ROOT / f"ppocrv5_accuracy_comparison_{target_platform}.md"
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    payload = {
        "target_platform": target_platform,
        "do_quantization": do_quantization,
        "summaries": summaries,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    by_case = {summary["case"]: summary for summary in summaries}
    lines = [
        f"# PP-OCRv5 Accuracy Comparison ({target_platform})",
        "",
        f"- do_quantization: {do_quantization}",
        "- accuracy_analysis: simulator",
        "",
        "| Case | Final output cos | Final output euc | Worst layer cos | Worst layer | Worst layer euc | Worst euc layer | Build errors |",
        "| --- | ---: | ---: | ---: | --- | ---: | --- | ---: |",
    ]
    for summary in summaries:
        final_row = summary["final_output"]
        worst_cos = summary["worst_entire_cos"]
        worst_euc = summary["worst_entire_euc"]
        lines.append(
            "| {case} | {final_cos:.5f} | {final_euc:.4f} | {worst_cos_val:.5f} | {worst_cos_name} | {worst_euc_val:.4f} | {worst_euc_name} | {error_count} |".format(
                case=summary["case"],
                final_cos=final_row["entire_cos"],
                final_euc=final_row["entire_euc"],
                worst_cos_val=worst_cos["entire_cos"],
                worst_cos_name=worst_cos["name"],
                worst_euc_val=worst_euc["entire_euc"],
                worst_euc_name=worst_euc["name"],
                error_count=len(summary["build_error_lines"]),
            )
        )

    detection_cases = [key for key in ("mobile_detection", "server_detection") if key in by_case]
    recognition_cases = [key for key in ("mobile_recognition", "server_recognition") if key in by_case]

    if detection_cases:
        lines.extend(["", "## Detection", ""])
        for key in detection_cases:
            summary = by_case[key]
            lines.append(
                "- {} final output: cos={:.5f}, euc={:.4f}".format(
                    key,
                    summary["final_output"]["entire_cos"],
                    summary["final_output"]["entire_euc"],
                )
            )

    if recognition_cases:
        lines.extend(["", "## Recognition", ""])
        for key in recognition_cases:
            summary = by_case[key]
            lines.append(
                "- {} final output: cos={:.5f}, euc={:.4f}".format(
                    key,
                    summary["final_output"]["entire_cos"],
                    summary["final_output"]["entire_euc"],
                )
            )

    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def run_case(case: dict, *, target_platform: str, do_quantization: bool, accuracy_analysis_target: str | None, device_id: str | None) -> None:
    acc_input = case["accuracy_input"]
    if not acc_input.exists():
        raise FileNotFoundError(f"Missing accuracy input for {case_key(case)}: {acc_input}")

    out_dir = accuracy_dir(case, target_platform)
    out_dir.mkdir(parents=True, exist_ok=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(CONVERTER),
        "--variant",
        case["variant"],
        "--model",
        case["model"],
        "--target-platform",
        target_platform,
        "--accuracy-analysis-input",
        str(acc_input),
        "--accuracy-analysis-output-dir",
        str(out_dir),
    ]
    if do_quantization:
        command.append("--do-quantization")
    if accuracy_analysis_target:
        command.extend(["--accuracy-analysis-target", accuracy_analysis_target])
    if device_id:
        command.extend(["--device-id", device_id])

    env = os.environ.copy()
    temp = tmp_dir(case, target_platform)
    temp.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(temp)
    env["TMP"] = str(temp)
    env["TEMP"] = str(temp)

    log_file = log_path(case, target_platform)
    print(f"==> {case_key(case)}")
    print(f"    command: {' '.join(command)}")
    print(f"    log: {log_file}")
    with log_file.open("w", encoding="utf-8") as handle:
        subprocess.run(
            command,
            check=True,
            cwd=ROOT,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )


def main() -> int:
    args = parse_args()
    selected_keys = set(args.cases or [case_key(case) for case in CASES])
    selected_cases = [case for case in CASES if case_key(case) in selected_keys]
    summaries = []
    for case in selected_cases:
        if not args.summary_only:
            run_case(
                case,
                target_platform=args.target_platform,
                do_quantization=args.do_quantization,
                accuracy_analysis_target=args.accuracy_analysis_target,
                device_id=args.device_id,
            )
        summaries.append(build_summary(case, args.target_platform))

    json_path, md_path = write_comparison_report(
        summaries,
        target_platform=args.target_platform,
        do_quantization=args.do_quantization,
    )
    print(f"comparison_json: {json_path}")
    print(f"comparison_md: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
