# Immich Face Recognition Export Tool

[![Python 3.x](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A Python tool to export face recognition data from Immich photo management system to DigiKam-compatible XMP format files.

## Other Tools

- `ppocrv5-rknn/`: unified one-click pipeline for PP-OCRv5 mobile/server det/rec model export and RKNN conversion.
- `ml-models-textual-rknn/`: utilities for validating `ml-models` textual ONNX/RKNN exports on RK3576 hardware.
- `immich-rk3576-tools/`: RK3576 machine-learning deployment helpers migrated from `immich` repo (`prepare/run`, bundle export, Docker deploy docs/scripts). Quick start: [`immich-rk3576-tools/README.md`](./immich-rk3576-tools/README.md)

## 🌟 Features

- **🔍 Face Recognition Data Export** - Retrieve complete face recognition data from Immich API
- **📁 Directory Structure Preservation** - Output files maintain original photo directory structure
- **🎯 DigiKam Compatible** - Generate standard XMP sidecar files, fully compatible with DigiKam
- **⚙️ Flexible Configuration** - Support JSON configuration files and environment variables
- **🔒 Security First** - Prefer Immich API key authentication; sensitive configurations are automatically git-ignored
- **📊 Detailed Statistics** - Generate comprehensive export statistics reports
- **🚀 Efficient Processing** - Smart batch processing, supports large photo libraries
- **🔄 Two-Stage Processing** - Export to JSON first, then generate XMP files (flexible workflow)
- **🎯 Debug-Friendly** - Support limiting processed assets quantity for testing

## 🚀 Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/yuhuan417/immich-scripts.git
cd immich-scripts
```

### 2. Install Dependencies
```bash
pip install requests
```

### 3. Configuration Setup

#### Method 1: Using Config File (Recommended)
```bash
# Copy template file
cp config.json.template config.json

# Edit configuration file
nano config.json
```

Fill in your Immich server information in `config.json`:
```json
{
  "immich": {
    "base_url": "https://your-immich-server.com",
    "api_key": "your-api-key",
    "email": "",
    "password": ""
  },
  "settings": {
    "request_timeout": 30,
    "retry_attempts": 3,
    "retry_backoff_seconds": 1
  },
  "output": {
    "digikam_xmp_dir": "digikam_xmp_sidecars",
    "json_export_dir": "json_exports"
  },
  "xmp": {
    "sidecar_naming": "extension-xmp",
    "include_unnamed_faces": false,
    "unnamed_face_name": "Unnamed Face",
    "write_dc_subject": true,
    "write_digikam_tags": false,
    "write_lightroom_hierarchical_subject": false,
    "people_tag_prefix": "People"
  },
  "search": {
    "asset_type": "IMAGE",
    "visibility": "timeline",
    "with_people": true
  }
}
```

#### Method 2: Using Environment Variables
```bash
export IMMICH_BASE_URL="https://your-immich-server.com"
export IMMICH_API_KEY="your-api-key"
```

`IMMICH_API_KEY` is the recommended authentication method. `IMMICH_EMAIL` and `IMMICH_PASSWORD` are still supported as a fallback for older setups.

### 4. Run Export

#### Basic Usage
```bash
# Run complete workflow (export to JSON then generate XMP)
python export_face.py
```

#### Advanced Usage
```bash
# Run only Stage 1: Export to JSON file
python export_face.py --stage1-only

# Run only Stage 2: Generate XMP from existing JSON file
python export_face.py --stage2-only --json-file path/to/export.json

# Limit processed assets for testing (e.g., process only 50 assets)
python export_face.py --max-assets 50

# Specify custom output directories
python export_face.py --json-dir my_json_exports --xmp-dir my_xmp_files

# Write sidecars beside the original files so Immich can detect them directly
python export_face.py --stage2-only --json-file path/to/export.json --write-next-to-original

# Include unnamed faces with a placeholder name (disabled by default)
python export_face.py --include-unnamed-faces

# Combine multiple options
python export_face.py --stage1-only --max-assets 100 --json-dir test_output
```

## 📖 Detailed Documentation

For the export design and compatibility plan, please refer to [DESIGN.md](DESIGN.md), which includes:

- 🔧 Immich API compatibility notes
- 🛠️ DigiKam/MWG XMP design
- 🔍 XML safety requirements
- 🛡️ Export validation plan
- 📋 Implementation migration steps

## 📁 Output Structure

After running the script, the following will be generated in the configured output directories:

### JSON Export (Stage 1)
```
json_exports/
├── immich_faces_export_20251013_143022.json  # Complete face data export
└── ...
```

### XMP Files (Stage 2)
```
digikam_xmp_sidecars/
├── export_summary.json          # Export statistics report
├── your-photo1.jpg.xmp         # XMP sidecar file
├── your-photo2.jpg.xmp
└── subdirectory/
    ├── photo3.jpg.xmp
    └── photo4.jpg.xmp
```

Immich detects sidecars at `originalPath + ".xmp"` first, for example `IMG_0001.jpg.xmp`, then falls back to `IMG_0001.xmp`. The default `extension-xmp` naming is chosen to match that preferred Immich and DigiKam sidecar form. Use `--write-next-to-original` only when the machine running the script can safely write to the original photo library path.

## 🎯 Use Cases

- **📸 Photo Management Migration** - Maintain face recognition data when migrating from Immich to DigiKam
- **🔖 Metadata Backup** - Backup face recognition information in standard XMP format
- **👥 People Tag Management** - Sync people tags between different photo management software
- **📊 Data Analysis** - Analyze person appearance frequency and distribution in photo libraries
- **🔄 Workflow Flexibility** - Two-stage processing allows data export and XMP generation to be performed separately
- **🧪 Development & Testing** - Limit processed assets for debugging and development purposes

## 🔧 Configuration Options

| Configuration Item | Environment Variable | Default Value | Description |
|--------------------|---------------------|---------------|-------------|
| `immich.base_url` | `IMMICH_BASE_URL` | - | Immich server address |
| `immich.api_key` | `IMMICH_API_KEY` | - | Immich API key (recommended) |
| `immich.email` | `IMMICH_EMAIL` | - | Login email (fallback only) |
| `immich.password` | `IMMICH_PASSWORD` | - | Login password (fallback only) |
| `settings.request_timeout` | `IMMICH_REQUEST_TIMEOUT` | 30 | API request timeout (seconds) |
| `settings.retry_attempts` | `IMMICH_RETRY_ATTEMPTS` | 3 | Number of retry attempts |
| `settings.retry_backoff_seconds` | `IMMICH_RETRY_BACKOFF_SECONDS` | 1 | Base retry backoff in seconds |
| `output.digikam_xmp_dir` | `OUTPUT_DIGIKAM_XMP_DIR` | digikam_xmp_sidecars | XMP output directory |
| `output.json_export_dir` | `OUTPUT_JSON_EXPORT_DIR` | json_exports | JSON export directory |
| `xmp.sidecar_naming` | `XMP_SIDECAR_NAMING` | extension-xmp | `extension-xmp` or `replace-extension` |
| `xmp.include_unnamed_faces` | `XMP_INCLUDE_UNNAMED_FACES` | false | Export unnamed faces with a placeholder |
| `xmp.write_dc_subject` | `XMP_WRITE_DC_SUBJECT` | true | Write person names as XMP subjects |
| `xmp.write_digikam_tags` | `XMP_WRITE_DIGIKAM_TAGS` | false | Write `digiKam:TagsList` people tags |
| `xmp.write_lightroom_hierarchical_subject` | `XMP_WRITE_LIGHTROOM_HIERARCHICAL_SUBJECT` | false | Write `lr:hierarchicalSubject` people tags |
| `xmp.people_tag_prefix` | `XMP_PEOPLE_TAG_PREFIX` | People | Prefix used for optional hierarchical people tags |
| `search.asset_type` | `IMMICH_SEARCH_ASSET_TYPE` | IMAGE | Asset type sent to Immich metadata search |
| `search.visibility` | `IMMICH_SEARCH_VISIBILITY` | timeline | Asset visibility sent to Immich metadata search |

## 🛠️ Development

### Code Checking
```bash
# Syntax check
python3 -m py_compile export_face.py

# Import test
python3 -c "from export_face import ConfigLoader; print('OK')"

# Unit tests
python3 -m unittest
```

### Configuration Testing
```bash
# Test environment variable configuration
export IMMICH_API_KEY="test-api-key"
python3 -c "from export_face import ConfigLoader; config = ConfigLoader(); print('Config OK')"
```

## 🐛 Common Issues

### Q: Authentication failed?
**A:** Check if the server address and API key are correct, and ensure the server is accessible. If you use the legacy fallback flow, also verify email and password.

### Q: No XMP files generated?
**A:** Confirm that your photos have face metadata in Immich and at least one named person. Unnamed faces are skipped by default because Immich ignores unnamed sidecar regions during face import.

### Q: Output directory permission error?
**A:** Ensure the script has permission to create and write to the configured output directory.

### Q: How to handle large photo libraries?
**A:** The script automatically paginates processing and supports large photo libraries. Processing progress will be displayed in real-time. For testing, you can use `--max-assets` parameter to limit the number of processed assets.

### Q: What is two-stage processing?
**A:** Two-stage processing allows you to:
1. First export all face recognition data to a JSON file (`--stage1-only`)
2. Then generate XMP files from that JSON data (`--stage2-only`)

This provides flexibility for workflows and allows you to review the exported data before generating XMP files.

### Q: How to test the script with a small subset of photos?
**A:** Use the `--max-assets` parameter to limit the number of assets processed, for example: `python export_face.py --max-assets 50` will only process 50 assets.

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details

## 🤝 Contributing

Issues and Pull Requests are welcome!

## 📞 Contact

For questions or suggestions, please create an issue on GitHub.

---

**⭐ If this project is helpful to you, please give it a Star!**
