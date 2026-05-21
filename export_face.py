#!/usr/bin/env python3
"""
Export Immich face metadata to JSON and DigiKam/Immich-readable XMP sidecars.

The XMP output is intentionally centered on MWG region metadata. Immich imports
sidecar faces through exiftool's RegionInfo structure, which requires
AppliedToDimensions and RegionList. DigiKam also understands this MWG face
region format.
"""

import argparse
import copy
import json
import os
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


DEFAULT_CONFIG: Dict[str, Any] = {
    "immich": {
        "base_url": "https://your-immich-server.com",
        "api_key": "",
        "email": "",
        "password": "",
    },
    "settings": {
        "request_timeout": 30,
        "retry_attempts": 3,
        "retry_backoff_seconds": 1,
    },
    "output": {
        "digikam_xmp_dir": "digikam_xmp_sidecars",
        "json_export_dir": "json_exports",
    },
    "xmp": {
        "sidecar_naming": "extension-xmp",
        "include_unnamed_faces": False,
        "unnamed_face_name": "Unnamed Face",
        "write_dc_subject": True,
        "write_digikam_tags": False,
        "write_lightroom_hierarchical_subject": False,
        "people_tag_prefix": "People",
    },
    "search": {
        "asset_type": "IMAGE",
        "visibility": "timeline",
        "with_people": True,
    },
}

ENV_MAPPINGS = {
    "IMMICH_BASE_URL": ("immich", "base_url"),
    "IMMICH_API_KEY": ("immich", "api_key"),
    "IMMICH_EMAIL": ("immich", "email"),
    "IMMICH_PASSWORD": ("immich", "password"),
    "IMMICH_REQUEST_TIMEOUT": ("settings", "request_timeout"),
    "IMMICH_RETRY_ATTEMPTS": ("settings", "retry_attempts"),
    "IMMICH_RETRY_BACKOFF_SECONDS": ("settings", "retry_backoff_seconds"),
    "OUTPUT_DIGIKAM_XMP_DIR": ("output", "digikam_xmp_dir"),
    "OUTPUT_JSON_EXPORT_DIR": ("output", "json_export_dir"),
    "XMP_SIDECAR_NAMING": ("xmp", "sidecar_naming"),
    "XMP_INCLUDE_UNNAMED_FACES": ("xmp", "include_unnamed_faces"),
    "XMP_WRITE_DC_SUBJECT": ("xmp", "write_dc_subject"),
    "XMP_WRITE_DIGIKAM_TAGS": ("xmp", "write_digikam_tags"),
    "XMP_WRITE_LIGHTROOM_HIERARCHICAL_SUBJECT": ("xmp", "write_lightroom_hierarchical_subject"),
    "XMP_PEOPLE_TAG_PREFIX": ("xmp", "people_tag_prefix"),
    "IMMICH_SEARCH_ASSET_TYPE": ("search", "asset_type"),
    "IMMICH_SEARCH_VISIBILITY": ("search", "visibility"),
}

RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
X_NS = "adobe:ns:meta/"
XMP_NS = "http://ns.adobe.com/xap/1.0/"
DC_NS = "http://purl.org/dc/elements/1.1/"
MWG_RS_NS = "http://www.metadataworkinggroup.com/schemas/regions/"
ST_DIM_NS = "http://ns.adobe.com/xap/1.0/sType/Dimensions#"
ST_AREA_NS = "http://ns.adobe.com/xmp/sType/Area#"
DIGIKAM_NS = "http://www.digikam.org/ns/1.0/"
LR_NS = "http://ns.adobe.com/lightroom/1.0/"

for prefix, uri in [
    ("x", X_NS),
    ("rdf", RDF_NS),
    ("xmp", XMP_NS),
    ("dc", DC_NS),
    ("mwg-rs", MWG_RS_NS),
    ("stDim", ST_DIM_NS),
    ("stArea", ST_AREA_NS),
    ("digiKam", DIGIKAM_NS),
    ("lr", LR_NS),
]:
    ET.register_namespace(prefix, uri)


def qname(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def coerce_env_value(raw: str, current_value: Any) -> Any:
    if isinstance(current_value, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current_value, int) and not isinstance(current_value, bool):
        return int(raw)
    if isinstance(current_value, float):
        return float(raw)
    return raw


def set_nested(data: Dict[str, Any], path: Iterable[str], value: Any) -> None:
    current = data
    parts = list(path)
    for key in parts[:-1]:
        current = current.setdefault(key, {})
    current[parts[-1]] = value


class ConfigLoader:
    """Configuration loader supporting JSON files and environment variables."""

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config_data = copy.deepcopy(DEFAULT_CONFIG)
        self.config_loaded = False
        self.load_config()

    def load_config(self) -> None:
        file_config: Dict[str, Any] = {}
        if os.path.exists(self.config_file):
            with open(self.config_file, "r", encoding="utf-8") as config_handle:
                file_config = json.load(config_handle)
            self.config_loaded = True

        self.config_data = deep_merge(DEFAULT_CONFIG, file_config)
        self._load_from_env()

    def _load_from_env(self) -> None:
        for env_name, config_path in ENV_MAPPINGS.items():
            raw_value = os.getenv(env_name)
            if raw_value is None:
                continue
            current_value = self.get(".".join(config_path))
            set_nested(self.config_data, config_path, coerce_env_value(raw_value, current_value))

    def get(self, path: str, default: Any = None) -> Any:
        current: Any = self.config_data
        for key in path.split("."):
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current

    def get_immich_config(self) -> Dict[str, str]:
        return {
            "base_url": str(self.get("immich.base_url", "")).rstrip("/"),
            "api_key": str(self.get("immich.api_key", "")),
            "email": str(self.get("immich.email", "")),
            "password": str(self.get("immich.password", "")),
        }

    def get_output_config(self) -> Dict[str, str]:
        return {
            "digikam_xmp_dir": str(self.get("output.digikam_xmp_dir", "digikam_xmp_sidecars")),
            "json_export_dir": str(self.get("output.json_export_dir", "json_exports")),
        }

    def get_settings_config(self) -> Dict[str, Any]:
        return {
            "request_timeout": int(self.get("settings.request_timeout", 30)),
            "retry_attempts": int(self.get("settings.retry_attempts", 3)),
            "retry_backoff_seconds": float(self.get("settings.retry_backoff_seconds", 1)),
        }

    def get_xmp_config(self) -> Dict[str, Any]:
        return {
            "sidecar_naming": self.get("xmp.sidecar_naming", "extension-xmp"),
            "include_unnamed_faces": bool(self.get("xmp.include_unnamed_faces", False)),
            "unnamed_face_name": str(self.get("xmp.unnamed_face_name", "Unnamed Face")),
            "write_dc_subject": bool(self.get("xmp.write_dc_subject", True)),
            "write_digikam_tags": bool(self.get("xmp.write_digikam_tags", False)),
            "write_lightroom_hierarchical_subject": bool(
                self.get("xmp.write_lightroom_hierarchical_subject", False)
            ),
            "people_tag_prefix": str(self.get("xmp.people_tag_prefix", "People")),
        }

    def get_search_config(self) -> Dict[str, Any]:
        return {
            "asset_type": self.get("search.asset_type", "IMAGE"),
            "visibility": self.get("search.visibility", "timeline"),
            "with_people": bool(self.get("search.with_people", True)),
        }

    def validate_immich_config(self) -> bool:
        immich = self.get_immich_config()
        base_url = immich["base_url"]
        api_key = immich["api_key"]
        email = immich["email"]
        password = immich["password"]

        if not base_url or base_url in {"https://www.blahblah.com", "https://your-immich-server.com"}:
            print("Configuration error: set immich.base_url or IMMICH_BASE_URL")
            return False

        if api_key and api_key != "your-api-key":
            return True

        if email and password and email != "your-email@example.com" and password != "your-password":
            return True

        print("Configuration error: set immich.api_key or fallback email/password credentials")
        return False

    def print_config_summary(self) -> None:
        immich = self.get_immich_config()
        settings = self.get_settings_config()
        xmp = self.get_xmp_config()
        auth_method = "API key" if immich["api_key"] else "email/password fallback"

        print("Configuration summary:")
        print(f"  Config file: {self.config_file if self.config_loaded else 'not found, using defaults/env'}")
        print(f"  Server URL: {immich['base_url']}")
        print(f"  Authentication: {auth_method}")
        print(f"  Timeout: {settings['request_timeout']}s")
        print(f"  Retry attempts: {settings['retry_attempts']}")
        print(f"  Sidecar naming: {xmp['sidecar_naming']}")


class ImmichApiError(RuntimeError):
    pass


class ImmichClient:
    """Small Immich API client with auth, timeout, and retry behavior."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        email: str = "",
        password: str = "",
        request_timeout: int = 30,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 1,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_base = f"{self.base_url}/api"
        self.api_key = api_key
        self.email = email
        self.password = password
        self.request_timeout = request_timeout
        self.retry_attempts = max(1, retry_attempts)
        self.retry_backoff_seconds = retry_backoff_seconds
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

        if self.api_key:
            self.session.headers.update({"x-api-key": self.api_key})

    def authenticate(self) -> None:
        if self.api_key:
            return

        if not self.email or not self.password:
            raise ImmichApiError("missing API key or email/password credentials")

        response = self.request(
            "POST",
            "/auth/login",
            json_body={"email": self.email, "password": self.password},
            authenticated=False,
        )
        access_token = response.get("accessToken") if isinstance(response, dict) else None
        if not access_token:
            raise ImmichApiError("authentication response did not contain accessToken")
        self.session.headers.update({"Cookie": f"immich_access_token={access_token}"})

    def request(
        self,
        method: str,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        authenticated: bool = True,
    ) -> Any:
        url = f"{self.api_base}{path}"
        last_error: Optional[BaseException] = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = self.session.request(
                    method,
                    url,
                    json=json_body,
                    params=params,
                    timeout=self.request_timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.retry_attempts:
                    self._sleep_before_retry(attempt)
                    continue
                raise ImmichApiError(f"{method} {path} failed: {exc}") from exc

            if response.status_code in {429, 500, 502, 503, 504} and attempt < self.retry_attempts:
                last_error = ImmichApiError(f"{method} {path} returned HTTP {response.status_code}")
                self._sleep_before_retry(attempt)
                continue

            if not response.ok:
                detail = response.text[:500]
                auth_note = " Check credentials." if authenticated and response.status_code in {401, 403} else ""
                raise ImmichApiError(f"{method} {path} returned HTTP {response.status_code}: {detail}{auth_note}")

            if not response.content:
                return None

            try:
                return response.json()
            except json.JSONDecodeError as exc:
                raise ImmichApiError(f"{method} {path} returned invalid JSON") from exc

        raise ImmichApiError(f"{method} {path} failed after retries: {last_error}")

    def _sleep_before_retry(self, attempt: int) -> None:
        time.sleep(self.retry_backoff_seconds * attempt)

    def search_assets(self, page: int, size: int, search_config: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "page": page,
            "size": size,
            "type": search_config.get("asset_type", "IMAGE"),
            "visibility": search_config.get("visibility", "timeline"),
            "withPeople": bool(search_config.get("with_people", True)),
        }
        return self.request("POST", "/search/metadata", json_body=payload)

    def get_asset(self, asset_id: str) -> Dict[str, Any]:
        return self.request("GET", f"/assets/{asset_id}")

    def get_faces(self, asset_id: str) -> List[Dict[str, Any]]:
        data = self.request("GET", "/faces", params={"id": asset_id})
        if not isinstance(data, list):
            raise ImmichApiError(f"GET /faces?id={asset_id} returned {type(data).__name__}, expected list")
        return data


def as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def get_all_asset_ids(
    client: ImmichClient,
    search_config: Dict[str, Any],
    max_assets: Optional[int] = None,
    page_size: int = 200,
) -> List[str]:
    asset_ids: List[str] = []
    page = 1

    print("Collecting asset IDs...")
    while True:
        if max_assets is not None and len(asset_ids) >= max_assets:
            break

        search_data = client.search_assets(page, page_size, search_config)
        assets_data = search_data.get("assets", {}) if isinstance(search_data, dict) else {}
        items = assets_data.get("items", [])

        if not items:
            break

        page_ids = [item.get("id") for item in items if item.get("id")]
        if max_assets is not None:
            page_ids = page_ids[: max_assets - len(asset_ids)]
        asset_ids.extend(page_ids)
        print(f"  Page {page}: collected {len(page_ids)} IDs, total {len(asset_ids)}")

        next_page = assets_data.get("nextPage")
        if not next_page:
            break
        try:
            page = int(next_page)
        except (TypeError, ValueError):
            raise ImmichApiError(f"invalid search nextPage value: {next_page!r}")

    print(f"Collected {len(asset_ids)} asset IDs")
    return asset_ids


def normalize_face(face: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    bbox = {
        "x1": as_int(face.get("boundingBoxX1")),
        "y1": as_int(face.get("boundingBoxY1")),
        "x2": as_int(face.get("boundingBoxX2")),
        "y2": as_int(face.get("boundingBoxY2")),
    }
    if any(value is None for value in bbox.values()):
        return None

    person = face.get("person") if isinstance(face.get("person"), dict) else {}
    person_name = str(person.get("name") or "").strip()

    return {
        "face_id": face.get("id", ""),
        "source_type": face.get("sourceType", ""),
        "person_id": person.get("id", "") if person else "",
        "person_name": person_name,
        "image_width": as_int(face.get("imageWidth")),
        "image_height": as_int(face.get("imageHeight")),
        "bounding_box": bbox,
    }


def normalize_asset(asset: Dict[str, Any], faces: List[Dict[str, Any]]) -> Dict[str, Any]:
    normalized_faces = []
    for face in faces:
        normalized = normalize_face(face)
        if normalized:
            normalized_faces.append(normalized)
    named_faces = sum(1 for face in normalized_faces if face.get("person_name"))

    return {
        "asset_id": asset.get("id", ""),
        "original_file_name": asset.get("originalFileName", ""),
        "original_path": asset.get("originalPath", ""),
        "width": as_int(asset.get("width")),
        "height": as_int(asset.get("height")),
        "faces": normalized_faces,
        "stats": {
            "total_faces": len(normalized_faces),
            "named_faces": named_faces,
            "unnamed_faces": len(normalized_faces) - named_faces,
        },
    }


def process_assets_with_faces(
    client: ImmichClient,
    search_config: Dict[str, Any],
    max_assets: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    asset_ids = get_all_asset_ids(client, search_config, max_assets)
    processed_assets: List[Dict[str, Any]] = []
    stats = {
        "assets_seen": len(asset_ids),
        "assets_with_faces": 0,
        "named_faces": 0,
        "unnamed_faces": 0,
        "skipped_assets": 0,
        "skipped_faces": 0,
    }

    print(f"Processing {len(asset_ids)} assets for face data...")
    for index, asset_id in enumerate(asset_ids, start=1):
        try:
            asset = client.get_asset(asset_id)
            faces = client.get_faces(asset_id)
        except ImmichApiError as exc:
            stats["skipped_assets"] += 1
            print(f"  Warning: skipped asset {asset_id}: {exc}")
            continue

        normalized = normalize_asset(asset, faces)
        if normalized["faces"]:
            processed_assets.append(normalized)
            stats["assets_with_faces"] += 1
            stats["named_faces"] += normalized["stats"]["named_faces"]
            stats["unnamed_faces"] += normalized["stats"]["unnamed_faces"]
            print(
                "  Asset "
                f"{stats['assets_with_faces']}: {normalized['original_file_name'] or asset_id} - "
                f"{normalized['stats']['total_faces']} faces"
            )

        if index % 20 == 0:
            print(f"  Progress: {index}/{len(asset_ids)} assets processed")

    return processed_assets, stats


def export_faces_to_json(
    client: ImmichClient,
    json_output_dir: str,
    search_config: Dict[str, Any],
    max_assets: Optional[int] = None,
) -> Optional[str]:
    output_path = Path(json_output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    processed_assets, stats = process_assets_with_faces(client, search_config, max_assets)
    if not processed_assets:
        print("No assets with faces found")
        return None

    export_data = {
        "schema_version": 2,
        "exported_at": now_iso(),
        "immich_server": client.base_url,
        "assets": processed_assets,
        "stats": stats,
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_file_path = output_path / f"immich_faces_export_{timestamp}.json"
    with open(json_file_path, "w", encoding="utf-8") as output_handle:
        json.dump(export_data, output_handle, indent=2, ensure_ascii=False)

    print("JSON export completed")
    print(f"  Assets with faces: {stats['assets_with_faces']}")
    print(f"  Named faces: {stats['named_faces']}")
    print(f"  Unnamed faces: {stats['unnamed_faces']}")
    print(f"  JSON file: {json_file_path}")
    return str(json_file_path)


def legacy_people_faces(asset_data: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for person in asset_data.get("people", []):
        if not isinstance(person, dict):
            continue
        person_name = str(person.get("name") or "").strip()
        person_id = str(person.get("id") or "")
        for face in person.get("faces", []):
            if not isinstance(face, dict):
                continue
            yield {
                "face_id": face.get("id", ""),
                "source_type": face.get("sourceType", ""),
                "person_id": person_id,
                "person_name": person_name,
                "image_width": as_int(face.get("imageWidth")) or as_int(asset_data.get("width")),
                "image_height": as_int(face.get("imageHeight")) or as_int(asset_data.get("height")),
                "bounding_box": {
                    "x1": as_int(face.get("boundingBoxX1")),
                    "y1": as_int(face.get("boundingBoxY1")),
                    "x2": as_int(face.get("boundingBoxX2")),
                    "y2": as_int(face.get("boundingBoxY2")),
                },
            }


def iter_asset_faces(asset_data: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    faces = asset_data.get("faces")
    if isinstance(faces, list):
        for face in faces:
            if isinstance(face, dict):
                yield face
        return
    yield from legacy_people_faces(asset_data)


def prepare_xmp_regions(
    asset_data: Dict[str, Any],
    xmp_config: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    include_unnamed = bool(xmp_config.get("include_unnamed_faces", False))
    unnamed_face_name = str(xmp_config.get("unnamed_face_name") or "Unnamed Face")
    candidate_regions: List[Dict[str, Any]] = []
    warnings: List[str] = []
    skipped_unnamed = 0
    skipped_invalid = 0

    for face in iter_asset_faces(asset_data):
        person_name = str(face.get("person_name") or "").strip()
        if not person_name:
            if not include_unnamed:
                skipped_unnamed += 1
                continue
            person_name = unnamed_face_name

        bbox = face.get("bounding_box") if isinstance(face.get("bounding_box"), dict) else {}
        x1 = as_int(bbox.get("x1"))
        y1 = as_int(bbox.get("y1"))
        x2 = as_int(bbox.get("x2"))
        y2 = as_int(bbox.get("y2"))
        image_width = as_int(face.get("image_width")) or as_int(asset_data.get("width"))
        image_height = as_int(face.get("image_height")) or as_int(asset_data.get("height"))

        if None in {x1, y1, x2, y2} or not image_width or not image_height:
            skipped_invalid += 1
            continue

        box_width = x2 - x1
        box_height = y2 - y1
        if image_width <= 0 or image_height <= 0 or box_width <= 0 or box_height <= 0:
            skipped_invalid += 1
            continue

        candidate_regions.append(
            {
                "name": person_name,
                "dimensions": (image_width, image_height),
                "x": clamp((x1 + box_width / 2) / image_width),
                "y": clamp((y1 + box_height / 2) / image_height),
                "w": clamp(box_width / image_width),
                "h": clamp(box_height / image_height),
            }
        )

    if not candidate_regions:
        return [], {
            "skipped_unnamed": skipped_unnamed,
            "skipped_invalid": skipped_invalid,
            "warnings": warnings,
        }

    dimension_counts = Counter(region["dimensions"] for region in candidate_regions)
    target_dimensions = dimension_counts.most_common(1)[0][0]
    regions = []
    skipped_dimension_mismatch = 0
    for region in candidate_regions:
        if region["dimensions"] != target_dimensions:
            skipped_dimension_mismatch += 1
            continue
        regions.append(region)

    if skipped_dimension_mismatch:
        warnings.append(
            "skipped "
            f"{skipped_dimension_mismatch} face(s) with dimensions different from "
            f"{target_dimensions[0]}x{target_dimensions[1]}"
        )

    return regions, {
        "dimensions": target_dimensions,
        "skipped_unnamed": skipped_unnamed,
        "skipped_invalid": skipped_invalid,
        "skipped_dimension_mismatch": skipped_dimension_mismatch,
        "warnings": warnings,
    }


def add_rdf_list(parent: ET.Element, property_name: str, values: List[str], bag_type: str = "Bag") -> None:
    element = ET.SubElement(parent, property_name)
    bag = ET.SubElement(element, qname(RDF_NS, bag_type))
    for value in values:
        ET.SubElement(bag, qname(RDF_NS, "li")).text = value


def build_digikam_xmp(
    asset_data: Dict[str, Any],
    xmp_config: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    config = dict(DEFAULT_CONFIG["xmp"])
    if xmp_config:
        config.update(xmp_config)

    regions, stats = prepare_xmp_regions(asset_data, config)
    if not regions:
        return "", stats

    image_width, image_height = stats["dimensions"]
    names = sorted({region["name"] for region in regions if region["name"]})
    created_at = now_iso()

    root = ET.Element(qname(X_NS, "xmpmeta"), {qname(X_NS, "xmptk"): "Immich Face Export Script"})
    rdf = ET.SubElement(root, qname(RDF_NS, "RDF"))
    description = ET.SubElement(rdf, qname(RDF_NS, "Description"), {qname(RDF_NS, "about"): ""})

    ET.SubElement(description, qname(XMP_NS, "CreatorTool")).text = "Immich Face Export Script"
    ET.SubElement(description, qname(XMP_NS, "MetadataDate")).text = created_at
    ET.SubElement(description, qname(XMP_NS, "ModifyDate")).text = created_at

    if names and config.get("write_dc_subject", True):
        add_rdf_list(description, qname(DC_NS, "subject"), names, "Bag")

    if names and config.get("write_digikam_tags", False):
        prefix = str(config.get("people_tag_prefix") or "").strip("/")
        tags = [f"{prefix}/{name}" if prefix else name for name in names]
        add_rdf_list(description, qname(DIGIKAM_NS, "TagsList"), tags, "Seq")

    if names and config.get("write_lightroom_hierarchical_subject", False):
        prefix = str(config.get("people_tag_prefix") or "").strip("|")
        tags = [f"{prefix}|{name}" if prefix else name for name in names]
        add_rdf_list(description, qname(LR_NS, "hierarchicalSubject"), tags, "Bag")

    regions_element = ET.SubElement(
        description,
        qname(MWG_RS_NS, "Regions"),
        {qname(RDF_NS, "parseType"): "Resource"},
    )
    applied = ET.SubElement(
        regions_element,
        qname(MWG_RS_NS, "AppliedToDimensions"),
        {qname(RDF_NS, "parseType"): "Resource"},
    )
    ET.SubElement(applied, qname(ST_DIM_NS, "w")).text = str(image_width)
    ET.SubElement(applied, qname(ST_DIM_NS, "h")).text = str(image_height)
    ET.SubElement(applied, qname(ST_DIM_NS, "unit")).text = "pixel"

    region_list = ET.SubElement(regions_element, qname(MWG_RS_NS, "RegionList"))
    bag = ET.SubElement(region_list, qname(RDF_NS, "Bag"))

    for region in regions:
        item = ET.SubElement(bag, qname(RDF_NS, "li"), {qname(RDF_NS, "parseType"): "Resource"})
        ET.SubElement(item, qname(MWG_RS_NS, "Name")).text = region["name"]
        ET.SubElement(item, qname(MWG_RS_NS, "Type")).text = "Face"
        area = ET.SubElement(item, qname(MWG_RS_NS, "Area"), {qname(RDF_NS, "parseType"): "Resource"})
        ET.SubElement(area, qname(ST_AREA_NS, "x")).text = f"{region['x']:.6f}"
        ET.SubElement(area, qname(ST_AREA_NS, "y")).text = f"{region['y']:.6f}"
        ET.SubElement(area, qname(ST_AREA_NS, "w")).text = f"{region['w']:.6f}"
        ET.SubElement(area, qname(ST_AREA_NS, "h")).text = f"{region['h']:.6f}"
        ET.SubElement(area, qname(ST_AREA_NS, "unit")).text = "normalized"

    ET.indent(root, space=" ")
    xml_body = ET.tostring(root, encoding="unicode", short_empty_elements=True)
    xmp_content = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_body}\n'
    ET.fromstring(xmp_content)

    stats.update(
        {
            "faces_written": len(regions),
            "people": names,
            "image_width": image_width,
            "image_height": image_height,
        }
    )
    return xmp_content, stats


def create_digikam_xmp_content(asset_data: Dict[str, Any]) -> str:
    """Backward-compatible wrapper for callers that only need the XMP string."""
    return build_digikam_xmp(asset_data)[0]


def sidecar_filename(original_path: str, sidecar_naming: str) -> str:
    original = Path(original_path)
    if sidecar_naming == "replace-extension":
        return f"{original.stem}.xmp"
    return f"{original.name}.xmp"


def output_sidecar_path(original_path: str, output_dir: str, sidecar_naming: str) -> Path:
    filename = sidecar_filename(original_path, sidecar_naming)
    original = Path(original_path)
    output_base = Path(output_dir)

    if not original_path:
        return output_base / filename

    parts = original.parts
    if len(parts) > 2:
        relative_dir = Path(*parts[1:-1])
        return output_base / relative_dir / filename
    return output_base / filename


def save_xmp_sidecar(
    original_path: str,
    xmp_content: str,
    output_dir: str,
    sidecar_naming: str = "extension-xmp",
    write_next_to_original: bool = False,
) -> Optional[Path]:
    if not xmp_content.strip():
        return None

    if write_next_to_original:
        target_path = Path(original_path).with_name(sidecar_filename(original_path, sidecar_naming))
    else:
        target_path = output_sidecar_path(original_path, output_dir, sidecar_naming)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as output_handle:
        output_handle.write(xmp_content)

    return target_path


def asset_original_path(asset_data: Dict[str, Any]) -> str:
    return str(
        asset_data.get("original_path")
        or asset_data.get("originalPath")
        or asset_data.get("original_file_name")
        or asset_data.get("file_name")
        or f"unknown_{asset_data.get('asset_id', 'asset')}.jpg"
    )


def export_faces_to_digikam_xmp_from_json(
    json_file_path: str,
    output_dir: str,
    xmp_config: Optional[Dict[str, Any]] = None,
    write_next_to_original: bool = False,
) -> bool:
    with open(json_file_path, "r", encoding="utf-8") as input_handle:
        export_data = json.load(input_handle)

    processed_assets = export_data.get("assets", [])
    if not processed_assets:
        print("No assets found in JSON file")
        return False

    config = dict(DEFAULT_CONFIG["xmp"])
    if xmp_config:
        config.update(xmp_config)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    total_files_created = 0
    total_faces_written = 0
    total_unnamed_skipped = 0
    total_invalid_skipped = 0
    people_stats: Dict[str, int] = {}
    warnings: List[str] = []

    print(f"Creating XMP files for {len(processed_assets)} assets...")
    for index, asset_data in enumerate(processed_assets, start=1):
        xmp_content, stats = build_digikam_xmp(asset_data, config)
        total_unnamed_skipped += int(stats.get("skipped_unnamed", 0))
        total_invalid_skipped += int(stats.get("skipped_invalid", 0))
        warnings.extend(str(warning) for warning in stats.get("warnings", []))

        if not xmp_content:
            continue

        original_path = asset_original_path(asset_data)
        target_path = save_xmp_sidecar(
            original_path,
            xmp_content,
            output_dir,
            sidecar_naming=str(config.get("sidecar_naming", "extension-xmp")),
            write_next_to_original=write_next_to_original,
        )
        if not target_path:
            continue

        total_files_created += 1
        total_faces_written += int(stats.get("faces_written", 0))
        for person in stats.get("people", []):
            people_stats[person] = people_stats.get(person, 0) + 1

        print(f"  Saved XMP sidecar: {target_path}")
        if index % 20 == 0:
            print(f"  Progress: {index}/{len(processed_assets)} assets")

    summary_file = Path(output_dir) / "export_summary.json"
    summary_data = {
        "exported_at": now_iso(),
        "json_source": json_file_path,
        "total_assets": len(processed_assets),
        "total_xmp_files_created": total_files_created,
        "total_faces_written": total_faces_written,
        "total_unnamed_faces_skipped": total_unnamed_skipped,
        "total_invalid_faces_skipped": total_invalid_skipped,
        "people_statistics": people_stats,
        "warnings": warnings,
        "output_directory": str(Path(output_dir).absolute()),
        "sidecar_naming": config.get("sidecar_naming", "extension-xmp"),
        "write_next_to_original": write_next_to_original,
    }
    with open(summary_file, "w", encoding="utf-8") as summary_handle:
        json.dump(summary_data, summary_handle, indent=2, ensure_ascii=False)

    print("XMP export completed")
    print(f"  XMP sidecar files created: {total_files_created}")
    print(f"  Faces written: {total_faces_written}")
    print(f"  Unnamed faces skipped: {total_unnamed_skipped}")
    print(f"  Invalid faces skipped: {total_invalid_skipped}")
    print(f"  Summary file: {summary_file}")

    return total_files_created > 0


def export_faces_to_digikam_xmp(
    client: ImmichClient,
    output_dir: str,
    search_config: Dict[str, Any],
    xmp_config: Dict[str, Any],
    max_assets: Optional[int] = None,
    write_next_to_original: bool = False,
) -> bool:
    processed_assets, stats = process_assets_with_faces(client, search_config, max_assets)
    if not processed_assets:
        print("No assets with faces found")
        return False

    temp_export = {
        "schema_version": 2,
        "exported_at": now_iso(),
        "immich_server": client.base_url,
        "assets": processed_assets,
        "stats": stats,
    }
    temp_json = Path(output_dir) / "latest_in_memory_export.json"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    with open(temp_json, "w", encoding="utf-8") as temp_handle:
        json.dump(temp_export, temp_handle, indent=2, ensure_ascii=False)
    return export_faces_to_digikam_xmp_from_json(str(temp_json), output_dir, xmp_config, write_next_to_original)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export face recognition data from Immich to JSON and DigiKam/Immich-readable XMP sidecars",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python export_face.py
  python export_face.py --stage1-only
  python export_face.py --stage2-only --json-file json_exports/immich_faces_export.json
  python export_face.py --max-assets 50
  python export_face.py --include-unnamed-faces
  python export_face.py --write-next-to-original
        """,
    )
    parser.add_argument("--stage1-only", action="store_true", help="export Immich face data to JSON only")
    parser.add_argument("--stage2-only", action="store_true", help="generate XMP files from an existing JSON export")
    parser.add_argument("--json-file", type=str, help="JSON file for --stage2-only")
    parser.add_argument("--json-dir", type=str, default=None, help="directory for JSON exports")
    parser.add_argument("--xmp-dir", type=str, default=None, help="directory for XMP output")
    parser.add_argument("--max-assets", type=int, default=None, help="maximum number of assets to scan")
    parser.add_argument(
        "--include-unnamed-faces",
        action="store_true",
        help="write unnamed faces using xmp.unnamed_face_name; off by default to avoid fake people",
    )
    parser.add_argument(
        "--sidecar-naming",
        choices=["extension-xmp", "replace-extension"],
        default=None,
        help="extension-xmp writes photo.jpg.xmp; replace-extension writes photo.xmp",
    )
    parser.add_argument("--write-digikam-tags", action="store_true", help="write digiKam:TagsList people tags")
    parser.add_argument(
        "--write-lightroom-hierarchical-subject",
        action="store_true",
        help="write lr:hierarchicalSubject people tags",
    )
    parser.add_argument(
        "--write-next-to-original",
        action="store_true",
        help="write XMP next to originalPath so Immich can detect it directly",
    )
    parser.add_argument("--config", default="config.json", help="configuration file path")
    return parser.parse_args()


def apply_cli_overrides(args: argparse.Namespace, xmp_config: Dict[str, Any]) -> Dict[str, Any]:
    config = dict(xmp_config)
    if args.include_unnamed_faces:
        config["include_unnamed_faces"] = True
    if args.sidecar_naming:
        config["sidecar_naming"] = args.sidecar_naming
    if args.write_digikam_tags:
        config["write_digikam_tags"] = True
    if args.write_lightroom_hierarchical_subject:
        config["write_lightroom_hierarchical_subject"] = True
    return config


def build_client_from_config(config: ConfigLoader) -> ImmichClient:
    immich = config.get_immich_config()
    settings = config.get_settings_config()
    return ImmichClient(
        base_url=immich["base_url"],
        api_key=immich["api_key"],
        email=immich["email"],
        password=immich["password"],
        request_timeout=settings["request_timeout"],
        retry_attempts=settings["retry_attempts"],
        retry_backoff_seconds=settings["retry_backoff_seconds"],
    )


def main() -> int:
    args = parse_arguments()

    if args.stage1_only and args.stage2_only:
        print("Error: cannot specify both --stage1-only and --stage2-only")
        return 2

    if args.stage2_only and not args.json_file:
        print("Error: --json-file is required with --stage2-only")
        return 2

    config = ConfigLoader(args.config)
    config.print_config_summary()

    output_config = config.get_output_config()
    xmp_config = apply_cli_overrides(args, config.get_xmp_config())
    search_config = config.get_search_config()
    json_dir = args.json_dir or output_config["json_export_dir"]
    xmp_dir = args.xmp_dir or output_config["digikam_xmp_dir"]

    if args.stage2_only:
        success = export_faces_to_digikam_xmp_from_json(
            args.json_file,
            xmp_dir,
            xmp_config,
            write_next_to_original=args.write_next_to_original,
        )
        return 0 if success else 1

    if not config.validate_immich_config():
        return 2

    client = build_client_from_config(config)
    try:
        client.authenticate()
    except ImmichApiError as exc:
        print(f"Authentication failed: {exc}")
        return 1

    print("Starting Immich face export")
    print(f"  JSON output directory: {json_dir}")
    print(f"  XMP output directory: {xmp_dir}")
    if args.write_next_to_original:
        print("  XMP write mode: next to original files")

    json_file_path = export_faces_to_json(client, json_dir, search_config, args.max_assets)
    if not json_file_path:
        return 1

    if args.stage1_only:
        return 0

    success = export_faces_to_digikam_xmp_from_json(
        json_file_path,
        xmp_dir,
        xmp_config,
        write_next_to_original=args.write_next_to_original,
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
