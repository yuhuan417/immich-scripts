# Immich Face Recognition Export Tool

[![Python 3.x](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A Python tool to export face recognition data from Immich photo management system to DigiKam-compatible XMP format files.

## Other Tools

- `ppocrv5-mobile-rknn/`: one-click pipeline for downloading official PP-OCRv5 mobile models, exporting ONNX, converting RKNN, and running accuracy analysis.

## 🌟 Features

- **🔍 Face Recognition Data Export** - Retrieve complete face recognition data from Immich API
- **📁 Directory Structure Preservation** - Output files maintain original photo directory structure
- **🎯 DigiKam Compatible** - Generate standard XMP sidecar files, fully compatible with DigiKam
- **⚙️ Flexible Configuration** - Support JSON configuration files and environment variables
- **🔒 Security First** - Sensitive configurations automatically git-ignored, protecting your authentication info
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
ano config.json
```

Fill in your Immich server information in `config.json`:
```json
{
  "immich": {
    "base_url": "https://your-immich-server.com",
    "email": "your-email@example.com",
    "password": "your-password"
  },
  "settings": {
    "request_timeout": 30,
    "retry_attempts": 3
  },
  "output": {
    "digikam_xmp_dir": "digikam_xmp_sidecars",
    "json_export_dir": "json_exports"
  }
}
```

#### Method 2: Using Environment Variables
```bash
export IMMICH_BASE_URL="https://your-immich-server.com"
export IMMICH_EMAIL="your-email@example.com"
export IMMICH_PASSWORD="your-password"
```

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

# Combine multiple options
python export_face.py --stage1-only --max-assets 100 --json-dir test_output
```

## 📖 Detailed Documentation

For complete project documentation, please refer to [IFLOW.md](IFLOW.md), which includes:

- 🔧 Complete configuration instructions
- 🛠️ Development guide
- 🔍 Troubleshooting
- 🛡️ Security best practices
- 📋 Detailed feature descriptions

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
| `immich.email` | `IMMICH_EMAIL` | - | Login email |
| `immich.password` | `IMMICH_PASSWORD` | - | Login password |
| `settings.request_timeout` | `IMMICH_REQUEST_TIMEOUT` | 30 | API request timeout (seconds) |
| `settings.retry_attempts` | `IMMICH_RETRY_ATTEMPTS` | 3 | Number of retry attempts |
| `output.digikam_xmp_dir` | `OUTPUT_DIGIKAM_XMP_DIR` | digikam_xmp_sidecars | XMP output directory |
| `output.json_export_dir` | `OUTPUT_JSON_EXPORT_DIR` | json_exports | JSON export directory |

## 🛠️ Development

### Code Checking
```bash
# Syntax check
python -m py_compile export_face.py

# Import test
python -c "from export_face import ConfigLoader; print('OK')"
```

### Configuration Testing
```bash
# Test environment variable configuration
export IMMICH_EMAIL="test@example.com"
export IMMICH_PASSWORD="testpass"
python -c "from export_face import ConfigLoader; config = ConfigLoader(); print('Config OK')"
```

## 🐛 Common Issues

### Q: Authentication failed?
**A:** Check if server address, email, and password are correct, and ensure the server is accessible.

### Q: No XMP files generated?
**A:** Confirm that your photos have been processed for face recognition in Immich. Only photos containing face data will generate XMP files.

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
