# Immich Thumbnail Fix Tool

## Project Overview

A simple Python script to fix missing thumbnails in Immich photo management systems. The tool identifies media files with missing thumbnail hashes and triggers thumbnail regeneration through the Immich API.

## Key Features

- **Simple Authentication**: Basic authentication with Immich API
- **Missing Thumbnail Detection**: Finds assets with null `thumbhash` values
- **Batch Processing**: Processes thumbnails in batches
- **Simple Error Handling**: Basic error handling and reporting

## Technology Stack

- **Language**: Python 3
- **Dependencies**:
  - `requests`: For HTTP API calls
  - `json`: For JSON data processing (Python standard library)

## Usage Instructions

### 1. Install Dependencies

```bash
pip install requests
```

### 2. Configure Authentication

Edit the script file `fix_immich_thumbnail.py` and fill in your Immich login credentials:

```python
EMAIL = "your-email@example.com"  # Your Immich email
PASSWORD = "your-password"        # Your Immich password
```

### 3. Update Server URL

Replace the URL in the script with your actual Immich server:

```python
IMMICH_BASE_URL = "https://your-immich-server.com"
```

### 4. Run the Script

```bash
python fix_immich_thumbnail.py
```

## Script Workflow

1. **Authentication**: Logs in and gets access token
2. **Search**: Finds assets missing thumbnail hashes
3. **Fix**: Triggers thumbnail regeneration for found assets

## Simple Configuration

The script uses these main configuration variables:

```python
# Update these in the script
IMMICH_BASE_URL = "https://your-immich-server.com"  # Your server URL
EMAIL = "your-email@example.com"                     # Your login email
PASSWORD = "your-password"                           # Your login password
```

## Output

The script shows:
- Number of assets found missing thumbnails
- Processing progress
- Success/failure status

## Simple Error Handling

Basic error handling for:
- Authentication failures
- Network errors
- API errors
- Missing thumbnails

## Code Structure

```
fix_immich_thumbnail.py
├── Configuration (URL, endpoints, headers)
├── Authentication (login function)
├── Asset Search (find missing thumbnails)
├── Thumbnail Fix (regenerate thumbnails)
└── Main execution flow
```

## Minimal Dependencies

Only requires the `requests` library - no complex dependencies or setup needed.