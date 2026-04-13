# PP-OCRv5 Unified RKNN Pipeline

This pipeline generates all PP-OCRv5 detection/recognition RKNN models in one run:

- mobile detection
- mobile recognition
- server detection
- server recognition

## What it does

1. Creates a dedicated export virtualenv for `paddlepaddle` + `paddle2onnx`
2. Creates a dedicated RKNN virtualenv for `rknn-toolkit2`
3. Downloads official Paddle inference models for all four PP-OCRv5 variants
4. Exports ONNX for all four models
5. Converts all ONNX models to RKNN in one pipeline
6. Sets `op_target={"exSoftmax13":"cpu"}` for recognition models
7. Writes a unified conversion report

## Entry Point

```bash
./tools/build_ppocrv5_rknn.sh --target-platform rk3576
```

## Outputs

- `PP-OCRv5_mobile_det/inference.onnx`
- `PP-OCRv5_mobile_rec/inference.onnx`
- `PP-OCRv5_server_det/inference.onnx`
- `PP-OCRv5_server_rec/inference.onnx`
- `detection/rknpu/<target_platform>/model.rknn`
- `recognition/rknpu/<target_platform>/model.rknn`
- `PP-OCRv5_server_det/rknpu/<target_platform>/model.rknn`
- `PP-OCRv5_server_rec/rknpu/<target_platform>/model.rknn`
- `output/rknn_conversion_report_ppocrv5.txt`

## Notes

- Conversion keeps `do_quantization=False`.
- `mean_values/std_values` are not baked into RKNN.
- Runtime preprocessing should stay external and consistent with each Paddle model.
