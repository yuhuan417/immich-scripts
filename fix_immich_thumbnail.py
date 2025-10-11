import requests
import json
from typing import Dict, Any, Optional

# Configuration
IMMICH_BASE_URL = "https://www.blahblah.com"
IMMICH_API_BASE = f"{IMMICH_BASE_URL}/api"

# API Endpoints
ENDPOINTS = {
    'login': f"{IMMICH_API_BASE}/auth/login",
    'search_metadata': f"{IMMICH_API_BASE}/search/metadata",
    'assets_jobs': f"{IMMICH_API_BASE}/assets/jobs"
}

# Default headers
DEFAULT_HEADERS = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}


def authenticate(email: str, password: str) -> Optional[str]:
    """Authenticate with Immich API and return access token."""
    payload = json.dumps({"email": email, "password": password})
    
    try:
        response = requests.post(ENDPOINTS['login'], headers=DEFAULT_HEADERS, data=payload)
        response.raise_for_status()
        return response.json()["accessToken"]
    except requests.exceptions.RequestException as e:
        print(f"Authentication failed: {e}")
        return None
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Failed to parse authentication response: {e}")
        return None


def get_auth_headers(access_token: str) -> Dict[str, str]:
    """Get headers with authentication cookie."""
    headers = DEFAULT_HEADERS.copy()
    headers['Cookie'] = f'immich_access_token={access_token}'
    return headers


def search_assets_without_thumbnails(access_token: str) -> list:
    """Search for assets missing thumbnail hashes."""
    asset_ids = []
    page = 1
    
    while True:
        payload = json.dumps({
            "isVisible": True,
            "page": page
        })
        
        try:
            response = requests.post(
                ENDPOINTS['search_metadata'], 
                headers=get_auth_headers(access_token), 
                data=payload
            )
            response.raise_for_status()
            
            assets_data = response.json()["assets"]
            
            for asset in assets_data["items"]:
                if asset.get("thumbhash") is None:
                    asset_ids.append(asset["id"])
            
            if assets_data.get("nextPage") is None:
                break
            page = assets_data["nextPage"]
            
        except requests.exceptions.RequestException as e:
            print(f"Error searching assets: {e}")
            break
        except (KeyError, json.JSONDecodeError) as e:
            print(f"Error parsing search response: {e}")
            break
    
    return asset_ids


def regenerate_thumbnails(access_token: str, asset_ids: list) -> bool:
    """Trigger thumbnail regeneration for specified assets."""
    if not asset_ids:
        print("No assets to process")
        return True
    
    payload = json.dumps({
        "assetIds": asset_ids,
        "name": "regenerate-thumbnail"
    })
    
    try:
        response = requests.post(
            ENDPOINTS['assets_jobs'],
            headers=get_auth_headers(access_token),
            data=payload
        )
        response.raise_for_status()
        
        print(f"Request payload: {payload}")
        print(f"Response: {response.text}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Error regenerating thumbnails: {e}")
        return False


def main():
    """Main function to orchestrate the thumbnail fix process."""
    # Configuration - Update these values
    EMAIL = ""  # Your Immich email
    PASSWORD = ""  # Your Immich password
    
    if not EMAIL or not PASSWORD:
        print("Please configure your EMAIL and PASSWORD in the main() function")
        return
    
    print("Starting Immich thumbnail fix process...")
    
    # Step 1: Authenticate
    access_token = authenticate(EMAIL, PASSWORD)
    if not access_token:
        return
    
    print("Authentication successful")
    
    # Step 2: Search for assets without thumbnails
    print("Searching for assets missing thumbnails...")
    asset_ids = search_assets_without_thumbnails(access_token)
    
    if not asset_ids:
        print("No assets found missing thumbnails")
        return
    
    print(f"Found {len(asset_ids)} assets missing thumbnails")
    
    # Step 3: Regenerate thumbnails
    print("Triggering thumbnail regeneration...")
    success = regenerate_thumbnails(access_token, asset_ids)
    
    if success:
        print(f"Successfully queued {len(asset_ids)} assets for thumbnail regeneration")
    else:
        print("Failed to regenerate thumbnails")


if __name__ == "__main__":
    main()
