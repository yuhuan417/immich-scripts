#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPARE_SCRIPT = ROOT / "tools" / "compare_textual_onnx_rknn.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run textual ONNX-vs-RKNN comparisons serially for multiple models.")
    parser.add_argument("--model", action="append", required=True, help="Model root directory name under models/. Repeatable.")
    parser.add_argument("--text-file", required=True, help="UTF-8 text file with one query per line.")
    parser.add_argument(
        "--ml-models-root",
        default=str(Path(__file__).resolve().parents[3] / "ml-models"),
        help="Path to the ml-models repository root.",
    )
    parser.add_argument("--target-platform", default="rk3576")
    parser.add_argument("--runtime-mode", choices=["ssh-rknnlite", "host-remote"], default="ssh-rknnlite")
    parser.add_argument("--host", default="192.168.1.202")
    parser.add_argument("--remote-python", default="/home/yuhuan/ml-models-rknn-venv/bin/python")
    parser.add_argument("--python-bin", default=sys.executable, help="Python executable used to run the compare script.")
    parser.add_argument(
        "--report-suffix",
        default="compare_1000.json",
        help="Report filename to write under each model's textual/rknpu/<platform>/ directory.",
    )
    parser.add_argument("--force", action="store_true", help="Re-run even if the target report already exists.")
    return parser.parse_args()


def report_path_for(ml_models_root: Path, model_name: str, target_platform: str, report_suffix: str) -> Path:
    return ml_models_root / "models" / model_name / "textual" / "rknpu" / target_platform / report_suffix


def main() -> int:
    args = parse_args()
    ml_models_root = Path(args.ml_models_root).resolve()
    summaries = []
    for model_name in args.model:
        report_path = report_path_for(ml_models_root, model_name, args.target_platform, args.report_suffix)
        if report_path.exists() and not args.force:
            data = json.loads(report_path.read_text())
            print(f"skip {model_name}: existing report {report_path}")
        else:
            cmd = [
                args.python_bin,
                COMPARE_SCRIPT.as_posix(),
                "--model-root",
                (ml_models_root / "models" / model_name).as_posix(),
                "--target-platform",
                args.target_platform,
                "--runtime-mode",
                args.runtime_mode,
                "--host",
                args.host,
                "--remote-python",
                args.remote_python,
                "--text-file",
                args.text_file,
                "--report-path",
                report_path.as_posix(),
            ]
            subprocess.run(cmd, check=True, cwd=ROOT)
            data = json.loads(report_path.read_text())

        summary = {
            "model": model_name,
            "report_path": report_path.as_posix(),
            "num_queries": data["num_queries"],
            "max_abs_diff": data["max_abs_diff"],
            "mean_abs_diff": data["mean_abs_diff"],
            "min_cosine_similarity": data["min_cosine_similarity"],
            "p95_max_abs_diff": data["max_abs_diff_stats"]["p95"],
            "p99_max_abs_diff": data["max_abs_diff_stats"]["p99"],
        }
        summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False))

    summary_path = ROOT / "output" / "bulk_textual_compare_summary.json"
    summary_path.write_text(json.dumps({"models": summaries}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
