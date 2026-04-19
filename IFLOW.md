# Immich Scripts - IFLOW Project Documentation

## Project Overview

This is a Python script for the Immich photo management system, used to export face recognition data from Immich into DigiKam-compatible XMP format files.

**Main Features:**
- Retrieve photo assets and face recognition data from Immich API
- Convert face data into DigiKam-compatible XMP sidecar files
- Support batch processing and directory structure preservation
- Provide configuration file management and environment variable support
- Built-in configuration loader (no separate config file needed)

**Core Technologies:**
- Python 3.x
- Requests library for API calls
- JSON configuration management
- XMP metadata format processing

## Project Structure

```
/Users/yuhuan/immich_scripts/
├── export_face.py           # Main export script with built-in configuration loader
├── config.json.template     # Configuration template file
├── digikam_xmp_sidecars/    # Output directory (XMP files)
│   └── myphoto/             # Sample photo directory structure
├── .gitignore               # Git ignore file configuration (includes config.json)
└── IFLOW.md                 # Project documentation (this file)
```

## Core Files Description

### export_face.py
The main export script that includes:
- Built-in configuration loader supporting JSON files and environment variables
- Immich API authentication with API key support and legacy login fallback
- Batch retrieval of photo asset IDs
- Get detailed face recognition data
- Generate DigiKam-compatible XMP sidecar files
- Preserve original directory structure
- Generate export statistics report

**Configuration Class Features:**
- Load configuration from JSON files
- Support environment variable override
- Configuration validation and default value handling
- Support nested configuration path access

### config.json.template
Configuration template file that provides:
- Example configuration structure
- All available configuration options
- Default values and descriptions
- Copy this file to `config.json` and customize for your needs

**Main Configuration Items:**
- `immich.base_url`: Immich server address
- `immich.api_key`: Immich API key (recommended)
- `immich.email`: Login email (fallback only)
- `immich.password`: Login password (fallback only)
- `settings.request_timeout`: Request timeout in seconds (default: 30)
- `settings.retry_attempts`: Retry attempts (default: 3)
- `output.digikam_xmp_dir`: XMP output directory (default: "digikam_xmp_sidecars")

## Configuration Management

### Configuration Security
- **config.json**: Actual configuration file (git-ignored for security)
- **config.json.template**: Template file with example values
- **Environment Variables**: Alternative to config.json for sensitive data

### Setup Instructions

1. **Copy the template file:**
   ```bash
   cp config.json.template config.json
   ```

2. **Edit config.json with your actual values:**
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
     "retry_attempts": 3
   },
     "output": {
       "digikam_xmp_dir": "digikam_xmp_sidecars"
     }
   }
   ```

3. **Or use environment variables (recommended for sensitive data):**
   ```bash
   export IMMICH_BASE_URL="https://your-immich-server.com"
   export IMMICH_API_KEY="your-api-key"
   ```

   `IMMICH_API_KEY` is the recommended authentication method. `IMMICH_EMAIL` and `IMMICH_PASSWORD` remain available as a fallback.

### Configuration Priority
1. Environment variables (highest priority)
2. config.json file
3. Built-in defaults (lowest priority)

## Usage Instructions

### 1. Initial Setup

```bash
# Copy template to create your configuration
cp config.json.template config.json

# Edit with your favorite editor
nano config.json
```

### 2. Run Export Script

```bash
python export_face.py
```

### 3. View Results

After export completion, the configured output directory will contain:
- XMP sidecar files (preserving original directory structure)
- `export_summary.json` export statistics report

## Development and Runtime Commands

### Basic Runtime
```bash
# Run main script directly
python export_face.py

# The script will automatically load config.json or use environment variables
```

### Testing and Validation
```bash
# Check Python syntax
python -m py_compile export_face.py

# Run basic import test
python -c "from export_face import ConfigLoader; print('Config loader OK')"

# Test with sample configuration
python -c "
import os
os.environ['IMMICH_API_KEY'] = 'test-api-key'
from export_face import ConfigLoader
config = ConfigLoader()
print('Environment config test OK')
"
```

## Development Conventions

### Code Style
- Use Python type annotations
- Follow PEP 8 naming conventions
- Functions and variables use lowercase with underscores
- Class names use camel case

### Error Handling
- Use try-except for API call exceptions
- Provide detailed error information and logs
- Support retry mechanism and timeout settings

### Configuration Management
- Built-in configuration loader (no separate file needed)
- Support both JSON files and environment variables
- Provide reasonable default values
- Configuration validation and error prompts
- Template file for easy setup

### Output Format
- XMP files use UTF-8 encoding
- Maintain compatibility with DigiKam
- Generate detailed export statistics

## Important Notes

1. **Configuration Security**: Never commit config.json to version control
2. **API Limits**: Pay attention to Immich API call frequency limits
3. **Directory Structure**: Output preserves original photo directory structure
5. **Face Data**: Only photos containing face data will generate XMP files
6. **Authentication**: Prefer a valid API key; ensure fallback login credentials are correct if you still use them
7. **Template Usage**: Always copy config.json.template to config.json before editing

## Security Best Practices

### Sensitive Data Protection
- config.json is automatically git-ignored
- Use environment variables for production deployments
- Prefer API keys over passwords where possible
- Never share your config.json file
- Rotate passwords regularly

### Template Management
- Keep config.json.template updated with new options
- Use template as documentation for available settings
- Document any configuration changes in your deployment

## Troubleshooting

### Common Issues
- **Authentication Failed**: Check server address and API key; if using fallback auth, also verify email and password
- **API Call Failed**: Check network connection and server status
- **Empty XMP Files**: Confirm photos contain face data
- **Directory Creation Failed**: Check write permissions for output directory
- **Configuration Errors**: Verify config.json format or environment variables
- **Config File Not Found**: Ensure you copied config.json.template to config.json

### Log Information
The script outputs detailed processing information, including:
- Configuration loading status
- API call progress
- File processing statistics
- Error and warning messages

## Recent Changes
- **Consolidated Configuration**: Removed separate config_loader.py, configuration functionality is now built into export_face.py
- **Simplified File Structure**: Single script file contains all functionality
- **Renamed**: export_digikam_efficient.py → export_face.py (shorter, more descriptive name)
- **Added Configuration Template**: config.json.template for easy setup and documentation
- **Enhanced Security**: Improved gitignore and security documentation
- **Removed Unused Features**: Removed thumbnail_fix_log and face_recognition_json configurations
- **Simplified Settings**: Streamlined configuration options to focus on core functionality
