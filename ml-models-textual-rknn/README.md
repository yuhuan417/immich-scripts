# ml-models textual RKNN validation

This directory contains board-side validation utilities for textual models exported from the sibling `ml-models` repository.

Scope:
- generate diverse multilingual text-query sets
- compare ONNX outputs against RKNN outputs on RK3576 hardware
- batch multiple textual model comparisons serially

The generic model export and RKNN conversion logic remains in `../ml-models`.

Main tools:
- `tools/generate_diverse_queries.py`
- `tools/compare_textual_onnx_rknn.py`
- `tools/run_bulk_textual_compare.py`
- `tools/run_multi_input_rknn_lite.py`
- `tools/run_multi_input_rknn_lite_dataset.py`

Typical usage:
```bash
python tools/generate_diverse_queries.py \
  --count 1000 \
  --output output/diverse_queries_1000.txt

python tools/run_bulk_textual_compare.py \
  --ml-models-root ../ml-models \
  --model XLM-Roberta-Base-ViT-B-32__laion5b_s13b_b90k \
  --text-file output/diverse_queries_1000.txt
```
