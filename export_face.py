#!/usr/bin/env python3
"""
Face recognition export script for Immich.
Uses search API to get asset IDs, then detailed API to get face data.
Exports face recognition data to DigiKam-compatible XMP format.
Supports two-stage processing: JSON export first, then XMP generation.
"""

import requests
import json
import os
import argparse
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path


class ConfigLoader:
    """Configuration loader that supports JSON files and environment variables."""
    
    def __init__(self, config_file: str = "config.json"):
        """Initialize configuration loader."""
        self.config_file = config_file
        self.config_data = {}
        self.load_config()
    
    def load_config(self) -> None:
        """Load configuration from file and environment variables."""
        # Load from JSON file if it exists
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config_data = json.load(f)
                print(f"✅ Configuration loaded from {self.config_file}")
            except (json.JSONDecodeError, IOError) as e:
                print(f"⚠️  Error loading config file {self.config_file}: {e}")
                print("   Using environment variables and defaults")
                self.config_data = {}
        else:
            print(f"⚠️  Config file {self.config_file} not found")
            print("   Using environment variables and defaults")
        
        # Override with environment variables if present
        self._load_from_env()
    
    def _load_from_env(self) -> None:
        """Load configuration from environment variables."""
        env_mappings = {
            'IMMICH_BASE_URL': ['immich', 'base_url'],
            'IMMICH_API_KEY': ['immich', 'api_key'],
            'IMMICH_EMAIL': ['immich', 'email'],
            'IMMICH_PASSWORD': ['immich', 'password'],
            'IMMICH_REQUEST_TIMEOUT': ['settings', 'request_timeout'],
            'IMMICH_RETRY_ATTEMPTS': ['settings', 'retry_attempts'],
            'OUTPUT_DIGIKAM_XMP_DIR': ['output', 'digikam_xmp_dir']
        }
        
        for env_var, config_path in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value:
                self._set_nested_value(self.config_data, config_path, env_value)
                print(f"✅ Loaded {env_var} from environment")
    
    def _set_nested_value(self, data: Dict[str, Any], path: list, value: str) -> None:
        """Set nested dictionary value from path list."""
        current = data
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Convert numeric values
        if path[-1] in ['request_timeout', 'retry_attempts']:
            try:
                current[path[-1]] = int(value)
            except ValueError:
                current[path[-1]] = value
        else:
            current[path[-1]] = value
    
    def get(self, path: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'immich.base_url')."""
        keys = path.split('.')
        current = self.config_data
        
        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default
    
    def get_immich_config(self) -> Dict[str, str]:
        """Get Immich connection configuration."""
        return {
            'base_url': self.get('immich.base_url', 'https://www.blahblah.com'),
            'api_key': self.get('immich.api_key', ''),
            'email': self.get('immich.email', ''),
            'password': self.get('immich.password', '')
        }
    
    def get_output_config(self) -> Dict[str, str]:
        """Get output configuration."""
        return {
            'digikam_xmp_dir': self.get('output.digikam_xmp_dir', 'digikam_xmp_sidecars'),
            'json_export_dir': self.get('output.json_export_dir', 'json_exports')
        }
    
    def get_settings_config(self) -> Dict[str, Any]:
        """Get general settings configuration."""
        return {
            'request_timeout': self.get('settings.request_timeout', 30),
            'retry_attempts': self.get('settings.retry_attempts', 3)
        }
    
    def validate_immich_config(self) -> bool:
        """Validate that required Immich configuration is present."""
        immich_config = self.get_immich_config()
        api_key = immich_config['api_key']
        email = immich_config['email']
        password = immich_config['password']
        base_url = immich_config['base_url']
        
        if base_url in {'https://www.blahblah.com', 'https://your-immich-server.com'}:
            print("❌ Configuration error: Please update the Immich server URL")
            print("   Set it in config.json or use environment variable:")
            print("   IMMICH_BASE_URL")
            return False

        if api_key and api_key != 'your-api-key':
            return True

        if email and password and email != 'your-email@example.com' and password != 'your-password':
            return True

        print("❌ Configuration error: Immich API key is required, or provide email/password as a fallback")
        print("   Recommended: set immich.api_key in config.json or export IMMICH_API_KEY")
        print("   Fallback: set IMMICH_EMAIL and IMMICH_PASSWORD")
        return False
    
    def print_config_summary(self) -> None:
        """Print a summary of loaded configuration."""
        auth_method = "API key" if self.get('immich.api_key') else "Email/password fallback"
        print("\n📋 Configuration Summary:")
        print(f"   Server URL: {self.get('immich.base_url')}")
        print(f"   Authentication: {auth_method}")
        if auth_method != "API key":
            print(f"   Email: {self.get('immich.email')}")
        print(f"   Timeout: {self.get('settings.request_timeout')}s")
        print(f"   Retry Attempts: {self.get('settings.retry_attempts')}")


# Global config loader instance
config = ConfigLoader()

# Get configuration from config file
immich_config = config.get_immich_config()
IMMICH_BASE_URL = immich_config['base_url']
IMMICH_API_BASE = f"{IMMICH_BASE_URL}/api"
output_config = config.get_output_config()

DEFAULT_HEADERS = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}


def authenticate_with_password(email: str, password: str) -> Optional[str]:
    """Authenticate with Immich using email/password and return access token."""
    payload = json.dumps({"email": email, "password": password})
    
    try:
        response = requests.post(f"{IMMICH_API_BASE}/auth/login", 
                               headers=DEFAULT_HEADERS, data=payload)
        response.raise_for_status()
        return response.json()["accessToken"]
    except requests.exceptions.RequestException as e:
        print(f"Authentication failed: {e}")
        return None
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Failed to parse authentication response: {e}")
        return None


def get_auth_headers(access_token: Optional[str] = None, api_key: Optional[str] = None) -> Dict[str, str]:
    """Build authenticated headers for either API key or access-token auth."""
    headers = DEFAULT_HEADERS.copy()

    if api_key:
        headers['x-api-key'] = api_key
    elif access_token:
        headers['Cookie'] = f'immich_access_token={access_token}'

    return headers


def create_auth_headers(immich_config: Dict[str, str]) -> Optional[Dict[str, str]]:
    """Create authenticated headers, preferring API key over password login."""
    api_key = immich_config.get('api_key', '')
    if api_key:
        return get_auth_headers(api_key=api_key)

    access_token = authenticate_with_password(
        immich_config.get('email', ''),
        immich_config.get('password', '')
    )
    if not access_token:
        return None

    return get_auth_headers(access_token=access_token)


def get_all_asset_ids(auth_headers: Dict[str, str], max_assets: Optional[int] = None) -> List[str]:
    """Get all asset IDs efficiently using search API."""
    asset_ids = []
    page = 1
    
    print("Collecting asset IDs...")
    
    while True:
        # Check if we've reached the maximum number of assets
        if max_assets is not None and len(asset_ids) >= max_assets:
            print(f"  Reached maximum asset limit: {max_assets}")
            break
        try:
            # Search for assets - just get basic info with IDs
            search_payload = {
                "page": page,
                "size": 200,  # Larger batch size for efficiency
                "isVisible": True
            }
            
            response = requests.post(
                f"{IMMICH_API_BASE}/search/metadata",
                headers=auth_headers,
                json=search_payload
            )
            response.raise_for_status()
            
            search_data = response.json()
            assets_data = search_data.get('assets', {})
            items = assets_data.get('items', [])
            
            if not items:
                break
                
            # Extract just the IDs
            page_ids = [item.get('id', '') for item in items if item.get('id')]
            
            # Apply max_assets limit if specified
            if max_assets is not None:
                remaining_slots = max_assets - len(asset_ids)
                if remaining_slots <= 0:
                    break
                # Only take what we need to reach the limit
                page_ids = page_ids[:remaining_slots]
            
            asset_ids.extend(page_ids)
            
            print(f"  Page {page}: Collected {len(page_ids)} IDs, total: {len(asset_ids)}")
            
            # Check next page
            next_page = assets_data.get('nextPage')
            if not next_page:
                print("  No more pages available")
                break
                
            try:
                page = int(next_page)
            except (ValueError, TypeError):
                print(f"Warning: Invalid nextPage value: {next_page}, stopping collection")
                break
            
        except requests.exceptions.RequestException as e:
            print(f"Error collecting asset IDs on page {page}: {e}")
            break
        except (KeyError, json.JSONDecodeError) as e:
            print(f"Error parsing ID collection response on page {page}: {e}")
            break
    
    print(f"✅ Collected {len(asset_ids)} asset IDs")
    return asset_ids


def get_asset_with_faces(auth_headers: Dict[str, str], asset_id: str) -> Optional[Dict[str, Any]]:
    """Get detailed asset info including face data."""
    try:
        response = requests.get(f"{IMMICH_API_BASE}/assets/{asset_id}", 
                              headers=auth_headers)
        response.raise_for_status()
        
        return response.json()
        
    except requests.exceptions.RequestException as e:
        print(f"Error getting asset {asset_id}: {e}")
        return None
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error parsing asset response {asset_id}: {e}")
        return None


def create_digikam_xmp_content(asset_data: Dict[str, Any]) -> str:
    """Create DigiKam-compatible XMP content for face recognition data with EXIF information."""
    
    # Get people data from asset
    people = asset_data.get('people', [])
    exif_info = asset_data.get('exifInfo', {})
    
    if not people:
        return ""
    
    # Extract EXIF data
    def safe_get_exif(key, default=""):
        return str(exif_info.get(key, default)) if exif_info.get(key) is not None else default
    
    # Format dates for XMP
    def format_xmp_date(date_str):
        if not date_str:
            return ""
        try:
            # Try to parse common date formats
            if 'T' in date_str:
                return date_str
            else:
                # Add time if only date
                return f"{date_str}T12:00:00"
        except:
            return date_str
    
    # Get camera information
    make = safe_get_exif('make')
    model = safe_get_exif('model')
    lens_model = safe_get_exif('lensModel')
    
    # Get exposure settings
    f_number = safe_get_exif('fNumber')
    exposure_time = safe_get_exif('exposureTime')
    iso = safe_get_exif('iso')
    focal_length = safe_get_exif('focalLength')
    
    # Get image dimensions
    image_width = safe_get_exif('exifImageWidth', '2160')
    image_height = safe_get_exif('exifImageHeight', '1440')
    
    # Get location information
    latitude = safe_get_exif('latitude')
    longitude = safe_get_exif('longitude')
    city = safe_get_exif('city')
    state = safe_get_exif('state')
    country = safe_get_exif('country')
    
    # Get dates
    date_original = format_xmp_date(safe_get_exif('dateTimeOriginal'))
    date_digitized = format_xmp_date(safe_get_exif('dateTimeDigitized'))
    
    # Get file info
    file_name = asset_data.get('file_name', '')
    original_path = asset_data.get('original_path', '')
    
    # XMP header with comprehensive namespaces
    xmp_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 4.4.0">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:mwg-rs="http://www.metadataworkinggroup.com/schemas/regions/"
   xmlns:dc="http://purl.org/dc/elements/1.1/"
   xmlns:xmp="http://ns.adobe.com/xap/1.0/"
   xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"
   xmlns:exif="http://ns.adobe.com/exif/1.0/"
   xmlns:tiff="http://ns.adobe.com/tiff/1.0/"
   xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/"
   xmlns:Iptc4xmpCore="http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/"
   xmlns:stDim="http://ns.adobe.com/xap/1.0/sType/Dimensions#"
   xmlns:stArea="http://ns.adobe.com/xap/1.0/sType/Area#"
   mwg-rs:Regions=""
   xmp:ModifyDate="{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
   xmp:MetadataDate="{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}">
'''
    
    # Add EXIF and TIFF information
    if make or model:
        xmp_content += f'''   <tiff:Make>{make}</tiff:Make>
   <tiff:Model>{model}</tiff:Model>
'''
    
    if lens_model:
        xmp_content += f'''   <exif:LensModel>{lens_model}</exif:LensModel>
'''
    
    # Add exposure settings
    if f_number:
        xmp_content += f'''   <exif:FNumber>{f_number}</exif:FNumber>
'''
    if exposure_time:
        xmp_content += f'''   <exif:ExposureTime>{exposure_time}</exif:ExposureTime>
'''
    if iso:
        xmp_content += f'''   <exif:ISOSpeedRatings>{iso}</exif:ISOSpeedRatings>
'''
    if focal_length:
        xmp_content += f'''   <exif:FocalLength>{focal_length}</exif:FocalLength>
'''
    
    # Add image dimensions
    if image_width and image_height:
        xmp_content += f'''   <tiff:ImageWidth>{image_width}</tiff:ImageWidth>
   <tiff:ImageLength>{image_height}</tiff:ImageLength>
   <exif:ExifImageWidth>{image_width}</exif:ExifImageWidth>
   <exif:ExifImageHeight>{image_height}</exif:ExifImageHeight>
'''
    
    # Add dates
    if date_original:
        xmp_content += f'''   <exif:DateTimeOriginal>{date_original}</exif:DateTimeOriginal>
'''
    if date_digitized:
        xmp_content += f'''   <exif:DateTimeDigitized>{date_digitized}</exif:DateTimeDigitized>
'''
    
    # Add location information
    if latitude and longitude:
        xmp_content += f'''   <exif:GPSLatitude>{latitude}</exif:GPSLatitude>
   <exif:GPSLongitude>{longitude}</exif:GPSLongitude>
'''
    
    # Add location names
    if city:
        xmp_content += f'''   <photoshop:City>{city}</photoshop:City>
'''
    if state:
        xmp_content += f'''   <photoshop:State>{state}</photoshop:State>
'''
    if country:
        xmp_content += f'''   <photoshop:Country>{country}</photoshop:Country>
'''
    
    # Add file information
    if file_name:
        xmp_content += f'''   <xmp:Identifier>{file_name}</xmp:Identifier>
'''
    if original_path:
        xmp_content += f'''   <xmp:BaseURL>{original_path}</xmp:BaseURL>
'''
    
    # Add software and creation info
    xmp_content += f'''   <xmp:CreatorTool>Immich Face Export Script</xmp:CreatorTool>
'''
    
    # Add people tags for general compatibility
    unique_people = set()
    for person in people:
        person_name = person.get('name', 'Unknown')
        if person_name and person_name != 'Unknown':
            unique_people.add(person_name)
    
    if unique_people:
        xmp_content += '''   <dc:subject>
    <rdf:Bag>
'''
        for person_name in sorted(unique_people):
            xmp_content += f'''     <rdf:li>{person_name}</rdf:li>
'''
        xmp_content += '''    </rdf:Bag>
   </dc:subject>
'''
    
    # Start face regions
    xmp_content += '''   <mwg-rs:Regions>
    <rdf:Bag>
'''
    
    # Add face regions from people data
    for person in people:
        person_name = person.get('name', 'Unknown')
        for face in person.get('faces', []):
            # Convert bounding box to XMP format (normalized coordinates)
            x1 = face.get('boundingBoxX1', 0)
            y1 = face.get('boundingBoxY1', 0)
            x2 = face.get('boundingBoxX2', 0)
            y2 = face.get('boundingBoxY2', 0)
            
            # Calculate center and dimensions
            width = x2 - x1
            height = y2 - y1
            center_x = x1 + width / 2
            center_y = y1 + height / 2
            
            # Get image dimensions for normalization
            exif_info = asset_data.get('exifInfo', {})
            image_width = int(exif_info.get('exifImageWidth', 2160))
            image_height = int(exif_info.get('exifImageHeight', 1440))
            
            # Normalize coordinates (0-1 range)
            norm_x = center_x / image_width if image_width > 0 else 0
            norm_y = center_y / image_height if image_height > 0 else 0
            norm_w = width / image_width if image_width > 0 else 0
            norm_h = height / image_height if image_height > 0 else 0
            
            # XMP region format
            region_xml = f'''     <rdf:li>
      <rdf:Description
       mwg-rs:Name="{person_name}"
       mwg-rs:Type="Face"
       mwg-rs:Extensions="">
       <mwg-rs:Area
        stArea:x="{norm_x:.6f}"
        stArea:y="{norm_y:.6f}"
        stArea:w="{norm_w:.6f}"
        stArea:h="{norm_h:.6f}"
        stArea:unit="normalized"/>
      </rdf:Description>
     </rdf:li>
'''
            xmp_content += region_xml
    
    # XMP footer
    xmp_content += '''    </rdf:Bag>
   </mwg-rs:Regions>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
'''
    
    return xmp_content


def save_xmp_sidecar(original_path: str, xmp_content: str, output_dir: str = "") -> bool:
    """Save XMP content to sidecar file, creating same directory structure in output_dir."""
    if not xmp_content.strip():
        return False  # Skip empty XMP
        
    try:
        # Create sidecar filename (same name with original extension + .xmp)
        original_path_obj = Path(original_path)
        filename = original_path_obj.name + '.xmp'
        
        if output_dir:
            output_base = Path(output_dir)
            
            # Extract relative path from original path
            # For: /myphoto/2025-09/yuhuan/file.jpg -> relative: 2025-09/yuhuan/file.xmp
            original_parts = original_path_obj.parts
            
            # Build relative directory structure (skip root like '/myphoto')
            if len(original_parts) > 2:  # Has subdirectories
                # Take all parts after the root directory
                relative_parts = original_parts[1:-1]  # Skip root and filename
                if relative_parts:
                    relative_dir = Path(*relative_parts)
                    xmp_path = output_base / relative_dir / filename
                else:
                    xmp_path = output_base / filename
            else:
                # Just filename, no subdirectories
                xmp_path = output_base / filename
            
            # Ensure the parent directories exist
            xmp_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            # If no output directory, use current directory
            xmp_path = Path(filename)
        
        with open(xmp_path, 'w', encoding='utf-8') as f:
            f.write(xmp_content)
        
        print(f"    Saved XMP sidecar: {xmp_path}")
        return True
        
    except IOError as e:
        print(f"    Error saving XMP file: {e}")
        return False


def process_assets_with_faces(auth_headers: Dict[str, str], max_assets: Optional[int] = None) -> List[Dict[str, Any]]:
    """Process assets and collect those with face recognition data."""
    processed_assets = []
    
    print("Step 1: Collecting asset IDs...")
    asset_ids = get_all_asset_ids(auth_headers, max_assets)
    
    if not asset_ids:
        print("No asset IDs collected")
        return processed_assets
    
    print(f"\nStep 2: Processing {len(asset_ids)} assets for face data...")
    
    # Apply max_assets limit to processing loop as well
    if max_assets is not None:
        asset_ids = asset_ids[:max_assets]
        print(f"  Limited to processing {len(asset_ids)} assets (max_assets limit)")
    
    # Process assets one by one to avoid hardcoded batch limits
    total_with_faces = 0
    
    for i, asset_id in enumerate(asset_ids):
        detailed_asset = get_asset_with_faces(auth_headers, asset_id)
        
        if detailed_asset:
            people = detailed_asset.get('people', [])
            
            if people and len(people) > 0:
                # Count total faces
                total_faces = sum(len(person.get('faces', [])) for person in people)
                
                file_name = detailed_asset.get('originalFileName', 'Unknown')
                print(f"    Asset {total_with_faces+1}: {file_name} - {len(people)} people, {total_faces} faces")
                
                # Prepare asset info
                asset_info = {
                    'asset_id': asset_id,
                    'original_path': detailed_asset.get('originalPath', ''),
                    'file_name': file_name,
                    'exifInfo': detailed_asset.get('exifInfo', {}),
                    'people': people  # Include people data directly in asset
                }
                
                processed_assets.append(asset_info)
                
                total_with_faces += 1
        
        # Progress update every 20 assets
        if (i + 1) % 20 == 0:
            print(f"    Progress: {i+1}/{len(asset_ids)} assets processed")
    
    print(f"\n✅ Processing completed: Found {total_with_faces} assets with faces")
    return processed_assets


def export_faces_to_json(auth_headers: Dict[str, str], json_output_dir: str = "json_exports", max_assets: Optional[int] = None) -> Optional[str]:
    """Export face recognition data to JSON file (Stage 1)."""
    print("Starting face recognition export to JSON format (Stage 1)...")
    
    # Create output directory
    output_path = Path(json_output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Process assets with faces
    processed_assets = process_assets_with_faces(auth_headers, max_assets)
    
    if not processed_assets:
        print("No assets with faces found")
        return None
    
    # Create comprehensive JSON export
    export_data = {
        'export_timestamp': datetime.now().isoformat(),
        'immich_server': IMMICH_BASE_URL,
        'total_assets': len(processed_assets),
        'assets': processed_assets
    }
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_filename = f"immich_faces_export_{timestamp}.json"
    json_file_path = output_path / json_filename
    
    try:
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ JSON export completed!")
        print(f"📊 Statistics:")
        print(f"   Total assets with faces: {len(processed_assets)}")
        print(f"   JSON file: {json_file_path}")
        
        return str(json_file_path)
        
    except IOError as e:
        print(f"❌ Error saving JSON file: {e}")
        return None


def export_faces_to_digikam_xmp_from_json(json_file_path: str, output_dir: str = "xmp_sidecars") -> bool:
    """Export face recognition data to DigiKam XMP format from JSON file (Stage 2)."""
    print(f"Starting face recognition export to DigiKam XMP format from JSON file (Stage 2)...")
    print(f"JSON source: {json_file_path}")
    
    try:
        # Load JSON data
        with open(json_file_path, 'r', encoding='utf-8') as f:
            export_data = json.load(f)
        
        processed_assets = export_data.get('assets', [])
        
        if not processed_assets:
            print("No assets found in JSON file")
            return False
        
        print(f"Loaded {len(processed_assets)} assets from JSON file")
        
    except (IOError, json.JSONDecodeError) as e:
        print(f"❌ Error loading JSON file: {e}")
        return False
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    total_files_created = 0
    total_faces_processed = 0
    person_stats = {}
    
    print(f"\nCreating XMP files for {len(processed_assets)} assets with faces...")
    
    for i, asset_data in enumerate(processed_assets):
        people_data = asset_data.get('people', [])
        
        if people_data:
            # Create XMP content
            xmp_content = create_digikam_xmp_content(asset_data)
            
            if xmp_content.strip():  # Only proceed if XMP content is not empty
                # Save XMP sidecar file
                original_path = asset_data.get('original_path', f"unknown_{asset_data['asset_id']}.jpg")
                if save_xmp_sidecar(original_path, xmp_content, str(output_path)):
                    total_files_created += 1
                    total_faces_processed += sum(len(person.get('faces', [])) for person in people_data)
                    
                    # Update person statistics
                    for person in people_data:
                        person_name = person.get('name', 'Unknown')
                        if person_name not in person_stats:
                            person_stats[person_name] = 0
                        person_stats[person_name] += len(person.get('faces', []))
                    
                    if (i + 1) % 5 == 0:  # Progress update every 5 files
                        print(f"    Progress: {i+1}/{len(processed_assets)} XMP files created")
            else:
                print(f"    Warning: Empty XMP content for asset {asset_data.get('file_name', 'Unknown')}")
        else:
            print(f"    Warning: No people data for asset {asset_data.get('file_name', 'Unknown')}")
    
    # Create summary file
    summary_file = output_path / "export_summary.json"
    summary_data = {
        'export_timestamp': datetime.now().isoformat(),
        'json_source': json_file_path,
        'total_assets': len(processed_assets),
        'total_xmp_files_created': total_files_created,
        'total_faces_processed': total_faces_processed,
        'people_statistics': person_stats,
        'output_directory': str(output_path.absolute())
    }
    
    try:
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"Error saving summary file: {e}")
    
    print(f"\n✅ DigiKam XMP export completed!")
    print(f"📊 Statistics:")
    print(f"   Total assets processed: {len(processed_assets)}")
    print(f"   XMP sidecar files created: {total_files_created}")
    print(f"   Total faces processed: {total_faces_processed}")
    print(f"   Unique people: {len(person_stats)}")
    print(f"   Output directory: {output_path.absolute()}")
    print(f"   Summary file: {summary_file}")
    
    # Print person statistics
    if person_stats:
        print(f"\n👥 People found:")
        for person, count in sorted(person_stats.items(), key=lambda x: x[1], reverse=True)[:20]:  # Top 20
            print(f"   {person}: {count} faces")
    
    return True


def export_faces_to_digikam_xmp(auth_headers: Dict[str, str], output_dir: str = "xmp_sidecars", max_assets: Optional[int] = None) -> bool:
    """Export face recognition data to DigiKam XMP sidecar files."""
    print("Starting face recognition export to DigiKam XMP format...")
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Process assets with faces
    processed_assets = process_assets_with_faces(auth_headers, max_assets)
    
    if not processed_assets:
        print("No assets with faces found")
        return False
    
    total_files_created = 0
    total_faces_processed = 0
    person_stats = {}
    
    print(f"\nCreating XMP files for {len(processed_assets)} assets with faces...")
    
    for i, asset_data in enumerate(processed_assets):
        people_data = asset_data.get('people', [])
        
        if people_data:
            # Create XMP content
            xmp_content = create_digikam_xmp_content(asset_data)
            
            if xmp_content.strip():  # Only proceed if XMP content is not empty
                # Save XMP sidecar file
                original_path = asset_data.get('original_path', f"unknown_{asset_data['asset_id']}.jpg")
                if save_xmp_sidecar(original_path, xmp_content, str(output_path)):
                    total_files_created += 1
                    total_faces_processed += sum(len(person.get('faces', [])) for person in people_data)
                    
                    # Update person statistics
                    for person in people_data:
                        person_name = person.get('name', 'Unknown')
                        if person_name not in person_stats:
                            person_stats[person_name] = 0
                        person_stats[person_name] += len(person.get('faces', []))
                    
                    if (i + 1) % 5 == 0:  # Progress update every 5 files
                        print(f"    Progress: {i+1}/{len(processed_assets)} XMP files created")
            else:
                print(f"    Warning: Empty XMP content for asset {asset_data.get('file_name', 'Unknown')}")
        else:
            print(f"    Warning: No people data for asset {asset_data.get('file_name', 'Unknown')}")
    
    # Create summary file
    summary_file = output_path / "export_summary.json"
    summary_data = {
        'export_timestamp': datetime.now().isoformat(),
        'total_assets': len(processed_assets),
        'total_xmp_files_created': total_files_created,
        'total_faces_processed': total_faces_processed,
        'people_statistics': person_stats,
        'output_directory': str(output_path.absolute())
    }
    
    try:
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"Error saving summary file: {e}")
    
    print(f"\n✅ DigiKam XMP export completed!")
    print(f"📊 Statistics:")
    print(f"   Total assets processed: {len(processed_assets)}")
    print(f"   XMP sidecar files created: {total_files_created}")
    print(f"   Total faces processed: {total_faces_processed}")
    print(f"   Unique people: {len(person_stats)}")
    print(f"   Output directory: {output_path.absolute()}")
    print(f"   Summary file: {summary_file}")
    
    # Print person statistics
    if person_stats:
        print(f"\n👥 People found:")
        for person, count in sorted(person_stats.items(), key=lambda x: x[1], reverse=True)[:20]:  # Top 20
            print(f"   {person}: {count} faces")
    
    return True


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Export face recognition data from Immich to DigiKam XMP format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Run both stages (default): Export to JSON then generate XMP
  python export_face.py
  
  # Run only Stage 1: Export to JSON file
  python export_face.py --stage1-only
  
  # Run only Stage 2: Generate XMP from existing JSON file
  python export_face.py --stage2-only --json-file path/to/export.json
  
  # Specify custom output directories
  python export_face.py --json-dir my_json_exports --xmp-dir my_xmp_files
        '''
    )
    
    parser.add_argument(
        '--stage1-only', 
        action='store_true',
        help='Run only Stage 1: Export face data to JSON file'
    )
    
    parser.add_argument(
        '--stage2-only',
        action='store_true', 
        help='Run only Stage 2: Generate XMP files from existing JSON file'
    )
    
    parser.add_argument(
        '--json-file',
        type=str,
        help='Path to JSON file for Stage 2 (required with --stage2-only)'
    )
    
    parser.add_argument(
        '--json-dir',
        type=str,
        default=None,
        help='Directory for JSON exports (default: from config)'
    )
    
    parser.add_argument(
        '--xmp-dir',
        type=str,
        default=None,
        help='Directory for XMP output (default: from config)'
    )
    
    parser.add_argument(
        '--max-assets',
        type=int,
        default=None,
        help='Maximum number of assets to process (for debugging)'
    )
    
    return parser.parse_args()


def main():
    """Main function to export face recognition data with two-stage processing."""
    args = parse_arguments()
    
    # Validate argument combinations
    if args.stage1_only and args.stage2_only:
        print("❌ Error: Cannot specify both --stage1-only and --stage2-only")
        return
    
    if args.stage2_only and not args.json_file:
        print("❌ Error: --json-file is required when using --stage2-only")
        return
    
    # Print configuration summary
    config.print_config_summary()
    
    # Stage 2 only mode - no need for Immich authentication
    if args.stage2_only:
        print("Running Stage 2 only: Generate XMP from JSON file")
        
        # Use custom XMP directory if specified, otherwise use config
        xmp_dir = args.xmp_dir or config.get_output_config()['digikam_xmp_dir']
        
        success = export_faces_to_digikam_xmp_from_json(args.json_file, xmp_dir)
        
        if success:
            print(f"\n🎉 XMP files generated successfully from JSON!")
            print(f"   Check the '{xmp_dir}' directory for XMP sidecar files.")
        else:
            print("\n❌ Failed to generate XMP files from JSON")
        return
    
    # Stage 1 or both stages - need Immich authentication
    if not config.validate_immich_config():
        return
    
    # Get configuration
    immich_config = config.get_immich_config()
    auth_headers = create_auth_headers(immich_config)
    output_config = config.get_output_config()
    
    # Use custom directories if specified, otherwise use config
    json_dir = args.json_dir or output_config['json_export_dir']
    xmp_dir = args.xmp_dir or output_config['digikam_xmp_dir']
    
    print("Starting Immich face recognition export...")
    print(f"Server: {IMMICH_BASE_URL}")
    print(f"JSON output directory: {json_dir}")
    print(f"XMP output directory: {xmp_dir}")
    if args.max_assets:
        print(f"Maximum assets to process: {args.max_assets}")
    
    # Step 1: Build authentication headers
    if not auth_headers:
        print("❌ Authentication failed. Please check your API key or fallback credentials.")
        return
    
    if immich_config['api_key']:
        print("✅ Using API key authentication")
    else:
        print("✅ Authentication successful via email/password fallback")
    
    # Stage 1: Export to JSON
    json_file_path = export_faces_to_json(auth_headers, json_dir, args.max_assets)
    
    if not json_file_path:
        print("❌ Failed to export face data to JSON")
        return
    
    if args.stage1_only:
        print(f"\n🎉 Stage 1 completed successfully!")
        print(f"   JSON file created: {json_file_path}")
        print(f"   Use this file with --stage2-only --json-file to generate XMP files later.")
        return
    
    # Stage 2: Generate XMP from JSON
    print(f"\nProceeding to Stage 2: Generate XMP files from JSON...")
    success = export_faces_to_digikam_xmp_from_json(json_file_path, xmp_dir)
    
    if success:
        print(f"\n🎉 Both stages completed successfully!")
        print(f"   JSON export: {json_file_path}")
        print(f"   XMP files: {xmp_dir}")
    else:
        print("\n❌ Failed to generate XMP files from JSON")


if __name__ == "__main__":
    main()
