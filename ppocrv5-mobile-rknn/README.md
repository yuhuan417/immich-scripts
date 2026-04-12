# PP-OCRv5 Mobile One-Click Pipeline

This pipeline starts from the official Paddle inference models and produces the
mobile RKNN artifacts plus accuracy-analysis reports.

## What it does

1. Creates a dedicated export virtualenv for `paddlepaddle` + `paddle2onnx`
2. Creates a dedicated RKNN virtualenv for `rknn-toolkit2`
3. Resolves the raw mobile Paddle inference models in this order:
   local extracted files -> local tar package -> explicit URL -> official model-name fallback
4. Exports `inference.onnx` for detection and recognition
5. Generates bundled accuracy-analysis inputs from the demo image in this repo
6. Converts the ONNX models to RKNN
7. Runs simulator-side `accuracy_analysis`
8. Writes a mobile-only comparison summary

## Entry point

```bash
./tools/build_ppocrv5_mobile_rknn.sh --target-platform rk3576
```

If `rknn-toolkit2` must be installed from a local wheel:

```bash
./tools/build_ppocrv5_mobile_rknn.sh \
  --target-platform rk3576 \
  --rknn-wheel /path/to/rknn_toolkit2-2.3.2-*.whl
```

## Outputs

- `PP-OCRv5_mobile_det/inference.onnx`
- `PP-OCRv5_mobile_rec/inference.onnx`
- `detection/rknpu/<target_platform>/model.rknn`
- `recognition/rknpu/<target_platform>/model.rknn`
- `output/accuracy_analysis/mobile/detection/<target_platform>/error_analysis.txt`
- `output/accuracy_analysis/mobile/recognition/<target_platform>/error_analysis.txt`
- `output/accuracy_analysis/ppocrv5_accuracy_comparison_<target_platform>.md`

## Notes

- The pipeline intentionally keeps `do_quantization=False`.
- Detection and recognition are converted in separate Python processes to keep
  memory pressure lower.
- The raw Paddle inference archives are downloaded into `artifacts/downloads/`
  and extracted into `artifacts/paddle_inference/`.
- The official model-name downloader is only used as a fallback when the local
  files and explicit URLs are unavailable.
