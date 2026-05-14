#!/usr/bin/env python3
"""
Conservative Immich duplicate resolver.

Default mode is dry-run. Use --execute to resolve matching duplicate groups.
Authentication and configuration follow export_face.py:
  - config.json by default
  - IMMICH_BASE_URL / IMMICH_API_KEY
  - IMMICH_EMAIL / IMMICH_PASSWORD fallback
"""

import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

import requests


DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}

PLACEHOLDER_BASE_URLS = {
    "https://www.blahblah.com",
    "https://your-immich-server.com",
}

SKIP_REASONS = {
    "not_two_assets": "group does not contain exactly two assets",
    "missing_size": "one or both assets are missing fileSizeInByte",
    "larger_has_less_exif": "larger asset has fewer EXIF values",
    "missing_date": "one or both asset dates are missing or invalid",
    "date_window_exceeded": "asset dates are farther apart than the configured window",
    "same_size_exif_and_date": "assets have equal size, equal EXIF count, and the same date",
}

AUTO_DATE_FIELDS = (
    "localDateTime",
    "fileCreatedAt",
    "exifInfo.dateTimeOriginal",
    "createdAt",
)


class ConfigLoader:
    """Configuration loader that supports JSON files and environment variables."""

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config_data: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> None:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.config_data = json.load(f)
                print(f"Configuration loaded from {self.config_file}")
            except (json.JSONDecodeError, OSError) as exc:
                print(f"Warning: failed to load {self.config_file}: {exc}")
                print("Using environment variables and defaults")
                self.config_data = {}
        else:
            print(f"Config file {self.config_file} not found")
            print("Using environment variables and defaults")

        self._load_from_env()

    def _load_from_env(self) -> None:
        env_mappings = {
            "IMMICH_BASE_URL": ["immich", "base_url"],
            "IMMICH_API_KEY": ["immich", "api_key"],
            "IMMICH_EMAIL": ["immich", "email"],
            "IMMICH_PASSWORD": ["immich", "password"],
            "IMMICH_REQUEST_TIMEOUT": ["settings", "request_timeout"],
            "IMMICH_RETRY_ATTEMPTS": ["settings", "retry_attempts"],
        }

        for env_var, config_path in env_mappings.items():
            env_value = os.getenv(env_var)
            if not env_value:
                continue

            self._set_nested_value(self.config_data, config_path, env_value)
            print(f"Loaded {env_var} from environment")

    def _set_nested_value(self, data: Dict[str, Any], path: List[str], value: str) -> None:
        current = data
        for key in path[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]

        if path[-1] in {"request_timeout", "retry_attempts"}:
            try:
                current[path[-1]] = int(value)
            except ValueError:
                current[path[-1]] = value
        else:
            current[path[-1]] = value

    def get(self, path: str, default: Any = None) -> Any:
        current: Any = self.config_data
        for key in path.split("."):
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current

    def get_immich_config(self) -> Dict[str, str]:
        return {
            "base_url": self.get("immich.base_url", "https://www.blahblah.com"),
            "api_key": self.get("immich.api_key", ""),
            "email": self.get("immich.email", ""),
            "password": self.get("immich.password", ""),
        }

    def get_settings_config(self) -> Dict[str, int]:
        return {
            "request_timeout": int(self.get("settings.request_timeout", 30)),
            "retry_attempts": int(self.get("settings.retry_attempts", 3)),
        }

    def validate_immich_config(self) -> bool:
        immich_config = self.get_immich_config()
        base_url = immich_config["base_url"].rstrip("/")
        api_key = immich_config["api_key"]
        email = immich_config["email"]
        password = immich_config["password"]

        if not base_url or base_url in PLACEHOLDER_BASE_URLS:
            print("Configuration error: set immich.base_url or IMMICH_BASE_URL")
            return False

        if api_key and api_key != "your-api-key":
            return True

        if email and password and email != "your-email@example.com" and password != "your-password":
            return True

        print("Configuration error: set immich.api_key or IMMICH_API_KEY")
        print("Fallback: set IMMICH_EMAIL and IMMICH_PASSWORD")
        return False


class ImmichClient:
    def __init__(self, base_url: str, headers: Dict[str, str], timeout: int, retry_attempts: int):
        self.api_base = f"{base_url.rstrip('/')}/api"
        self.headers = headers
        self.timeout = timeout
        self.retry_attempts = max(1, retry_attempts)

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.api_base}{path}"
        last_error: Optional[BaseException] = None

        for attempt in range(self.retry_attempts):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout,
                )

                if response.status_code >= 500 and attempt + 1 < self.retry_attempts:
                    time.sleep(min(2**attempt, 5))
                    continue

                response.raise_for_status()
                if response.status_code == 204 or not response.content:
                    return None
                return response.json()
            except (requests.exceptions.RequestException, json.JSONDecodeError) as exc:
                last_error = exc
                response = getattr(exc, "response", None)
                if response is not None and 400 <= response.status_code < 500:
                    raise
                if attempt + 1 < self.retry_attempts:
                    time.sleep(min(2**attempt, 5))
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError(f"request failed: {method} {path}")

    def get_duplicates(self) -> List[Dict[str, Any]]:
        data = self.request("GET", "/duplicates")
        if not isinstance(data, list):
            raise RuntimeError("unexpected /duplicates response: expected a list")
        return data

    def get_server_features(self) -> Dict[str, Any]:
        data = self.request("GET", "/server/features")
        if not isinstance(data, dict):
            raise RuntimeError("unexpected /server/features response: expected an object")
        return data

    def resolve_duplicates(self, groups: List[Dict[str, Any]], batch_size: int) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for batch_index, batch in enumerate(chunked(groups, batch_size), start=1):
            print(f"Resolving batch {batch_index}: {len(batch)} duplicate groups")
            try:
                data = self.request("POST", "/duplicates/resolve", {"groups": batch})
            except requests.exceptions.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code == 404:
                    print("Server does not support /duplicates/resolve; using legacy fallback.")
                    return self.resolve_duplicates_legacy(groups)
                raise

            if not isinstance(data, list):
                raise RuntimeError("unexpected /duplicates/resolve response: expected a list")
            results.extend(data)
        return results

    def resolve_duplicates_legacy(self, groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        for index, group in enumerate(groups, start=1):
            duplicate_id = str(group["duplicateId"])
            trash_asset_ids = list(group["trashAssetIds"])

            print(f"Resolving legacy group {index}/{len(groups)}: {duplicate_id}")
            try:
                self.request("DELETE", "/assets", {"ids": trash_asset_ids, "force": False})
                self.request("DELETE", f"/duplicates/{quote(duplicate_id, safe='')}")
                results.append({"id": duplicate_id, "success": True})
            except requests.exceptions.HTTPError as exc:
                error_message = str(exc)
                try:
                    response_data = exc.response.json() if exc.response is not None else None
                except json.JSONDecodeError:
                    response_data = None

                if isinstance(response_data, dict):
                    message = response_data.get("message")
                    if isinstance(message, list):
                        error_message = "; ".join(str(item) for item in message)
                    elif message:
                        error_message = str(message)

                results.append(
                    {
                        "id": duplicate_id,
                        "success": False,
                        "error": "legacy_fallback_failed",
                        "errorMessage": error_message,
                    }
                )

        return results


@dataclass(frozen=True)
class Candidate:
    duplicate_id: str
    keep_asset_id: str
    trash_asset_id: str
    keep_size: int
    trash_size: int
    keep_exif_count: int
    trash_exif_count: int
    date_delta: timedelta
    keep_name: str
    trash_name: str

    def to_resolve_group(self) -> Dict[str, Any]:
        return {
            "duplicateId": self.duplicate_id,
            "keepAssetIds": [self.keep_asset_id],
            "trashAssetIds": [self.trash_asset_id],
        }


def authenticate_with_password(
    base_url: str,
    email: str,
    password: str,
    timeout: int,
    retry_attempts: int,
) -> Optional[str]:
    api_base = f"{base_url.rstrip('/')}/api"
    client = ImmichClient(base_url, DEFAULT_HEADERS.copy(), timeout, retry_attempts)
    try:
        response = client.request("POST", "/auth/login", {"email": email, "password": password})
    except (requests.exceptions.RequestException, json.JSONDecodeError, RuntimeError) as exc:
        print(f"Authentication failed against {api_base}/auth/login: {exc}")
        return None

    if not isinstance(response, dict) or "accessToken" not in response:
        print("Authentication failed: response did not contain accessToken")
        return None
    return str(response["accessToken"])


def create_auth_headers(
    immich_config: Dict[str, str],
    timeout: int,
    retry_attempts: int,
) -> Optional[Dict[str, str]]:
    headers = DEFAULT_HEADERS.copy()
    api_key = immich_config.get("api_key", "")

    if api_key:
        headers["x-api-key"] = api_key
        return headers

    access_token = authenticate_with_password(
        immich_config.get("base_url", ""),
        immich_config.get("email", ""),
        immich_config.get("password", ""),
        timeout,
        retry_attempts,
    )
    if not access_token:
        return None

    headers["Cookie"] = f"immich_access_token={access_token}"
    return headers


def chunked(items: List[Dict[str, Any]], size: int) -> Iterable[List[Dict[str, Any]]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def js_truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0 and not (isinstance(value, float) and math.isnan(value))
    if isinstance(value, str):
        return value != ""
    return True


def get_exif_count(asset: Dict[str, Any]) -> int:
    exif_info = asset.get("exifInfo")
    if not isinstance(exif_info, dict):
        return 0
    return sum(1 for value in exif_info.values() if js_truthy(value))


def get_file_size(asset: Dict[str, Any]) -> Optional[int]:
    exif_info = asset.get("exifInfo")
    if not isinstance(exif_info, dict):
        return None

    value = exif_info.get("fileSizeInByte")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if value >= 0 and value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
    return None


def get_nested_value(data: Dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def parse_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def get_asset_date(asset: Dict[str, Any], date_field: str) -> Optional[datetime]:
    if date_field == "auto":
        for field in AUTO_DATE_FIELDS:
            parsed = parse_datetime(get_nested_value(asset, field))
            if parsed is not None:
                return parsed
        return None

    if date_field == "dateTimeOriginal":
        date_field = "exifInfo.dateTimeOriginal"
    return parse_datetime(get_nested_value(asset, date_field))


def analyze_group(
    group: Dict[str, Any],
    max_date_delta: timedelta,
    date_field: str,
) -> Tuple[Optional[Candidate], Optional[str]]:
    assets = group.get("assets")
    if not isinstance(assets, list) or len(assets) != 2:
        return None, "not_two_assets"

    first, second = assets
    if not isinstance(first, dict) or not isinstance(second, dict):
        return None, "not_two_assets"

    first_size = get_file_size(first)
    second_size = get_file_size(second)
    if first_size is None or second_size is None:
        return None, "missing_size"

    first_exif_count = get_exif_count(first)
    second_exif_count = get_exif_count(second)

    if first_size != second_size:
        if first_size > second_size:
            keep_asset, trash_asset = first, second
            keep_size, trash_size = first_size, second_size
            keep_exif_count, trash_exif_count = first_exif_count, second_exif_count
        else:
            keep_asset, trash_asset = second, first
            keep_size, trash_size = second_size, first_size
            keep_exif_count, trash_exif_count = second_exif_count, first_exif_count

        if keep_exif_count < trash_exif_count:
            return None, "larger_has_less_exif"
    else:
        if first_exif_count > second_exif_count:
            keep_asset, trash_asset = first, second
            keep_exif_count, trash_exif_count = first_exif_count, second_exif_count
        elif second_exif_count > first_exif_count:
            keep_asset, trash_asset = second, first
            keep_exif_count, trash_exif_count = second_exif_count, first_exif_count
        else:
            first_date = get_asset_date(first, date_field)
            second_date = get_asset_date(second, date_field)
            if first_date is None or second_date is None:
                return None, "missing_date"

            date_delta = abs(first_date - second_date)
            if date_delta > max_date_delta:
                return None, "date_window_exceeded"
            if first_date == second_date:
                return None, "same_size_exif_and_date"

            if first_date < second_date:
                keep_asset, trash_asset = first, second
            else:
                keep_asset, trash_asset = second, first

            keep_exif_count = trash_exif_count = first_exif_count

        keep_size = trash_size = first_size

    keep_date = get_asset_date(keep_asset, date_field)
    trash_date = get_asset_date(trash_asset, date_field)
    if keep_date is None or trash_date is None:
        return None, "missing_date"

    date_delta = abs(keep_date - trash_date)
    if date_delta > max_date_delta:
        return None, "date_window_exceeded"

    duplicate_id = group.get("duplicateId")
    keep_asset_id = keep_asset.get("id")
    trash_asset_id = trash_asset.get("id")
    if not duplicate_id or not keep_asset_id or not trash_asset_id:
        return None, "not_two_assets"

    return (
        Candidate(
            duplicate_id=str(duplicate_id),
            keep_asset_id=str(keep_asset_id),
            trash_asset_id=str(trash_asset_id),
            keep_size=keep_size,
            trash_size=trash_size,
            keep_exif_count=keep_exif_count,
            trash_exif_count=trash_exif_count,
            date_delta=date_delta,
            keep_name=str(keep_asset.get("originalFileName") or ""),
            trash_name=str(trash_asset.get("originalFileName") or ""),
        ),
        None,
    )


def analyze_duplicates(
    duplicate_groups: List[Dict[str, Any]],
    max_date_delta: timedelta,
    date_field: str,
) -> Tuple[List[Candidate], Counter]:
    candidates: List[Candidate] = []
    skipped: Counter = Counter()

    for group in duplicate_groups:
        candidate, skip_reason = analyze_group(group, max_date_delta, date_field)
        if candidate is not None:
            candidates.append(candidate)
        elif skip_reason:
            skipped[skip_reason] += 1

    return candidates, skipped


def print_summary(
    total_groups: int,
    candidates: List[Candidate],
    skipped: Counter,
    dry_run: bool,
) -> None:
    skipped_total = sum(skipped.values())
    assets_to_trash = len(candidates)

    print("")
    print("Summary")
    print(f"  Mode: {'dry-run' if dry_run else 'execute'}")
    print(f"  Duplicate groups scanned: {total_groups}")
    print(f"  Groups without a safe best choice: {skipped_total}")
    print(f"  Duplicate groups processable: {len(candidates)}")
    print(f"  Assets expected to move to trash: {assets_to_trash}")

    if skipped:
        print("")
        print("Skipped groups by reason")
        for reason, count in skipped.most_common():
            label = SKIP_REASONS.get(reason, reason)
            print(f"  {reason}: {count} ({label})")


def print_actions(candidates: List[Candidate], limit: int) -> None:
    if not candidates:
        return

    print("")
    print(f"Planned actions (showing first {min(limit, len(candidates))} of {len(candidates)})")
    for candidate in candidates[:limit]:
        print(
            "  "
            f"{candidate.duplicate_id}: keep {candidate.keep_asset_id} "
            f"({candidate.keep_size} bytes, exif {candidate.keep_exif_count}, {candidate.keep_name}) "
            f"trash {candidate.trash_asset_id} "
            f"({candidate.trash_size} bytes, exif {candidate.trash_exif_count}, {candidate.trash_name}) "
            f"date_delta={candidate.date_delta}"
        )


def print_execute_results(results: List[Dict[str, Any]]) -> bool:
    success_count = 0
    failures: List[Dict[str, Any]] = []

    for result in results:
        if result.get("success"):
            success_count += 1
        else:
            failures.append(result)

    print("")
    print("Execution result")
    print(f"  Groups resolved: {success_count}")
    print(f"  Groups failed: {len(failures)}")

    for failure in failures[:20]:
        print(
            "  failed "
            f"{failure.get('id')}: {failure.get('error')}"
            f"{' - ' + failure.get('errorMessage') if failure.get('errorMessage') else ''}"
        )

    if len(failures) > 20:
        print(f"  ... {len(failures) - 20} more failures omitted")

    return not failures


def ensure_trash_enabled(client: ImmichClient) -> bool:
    try:
        features = client.get_server_features()
    except (requests.exceptions.RequestException, json.JSONDecodeError, RuntimeError) as exc:
        print(f"Failed to verify server trash feature: {exc}")
        return False

    if features.get("trash") is True:
        return True

    print("Server trash feature is disabled; aborting to avoid permanent deletion.")
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve only safe two-asset Immich duplicate groups by choosing the best asset to keep.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 deduplicate.py
  python3 deduplicate.py --dry-run --list-actions
  python3 deduplicate.py --execute
""",
    )
    parser.add_argument("--config", default="config.json", help="Path to config JSON file")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        "--dryrun",
        dest="dry_run",
        action="store_true",
        help="Only analyze and print statistics. This is the default.",
    )
    mode_group.add_argument(
        "--execute",
        action="store_true",
        help="Apply the planned duplicate resolutions.",
    )
    parser.add_argument(
        "--date-field",
        default="localDateTime",
        choices=["localDateTime", "fileCreatedAt", "createdAt", "dateTimeOriginal", "exifInfo.dateTimeOriginal", "auto"],
        help="Asset date field used for the 3-day rule. Default: localDateTime.",
    )
    parser.add_argument(
        "--date-window-days",
        type=float,
        default=3.0,
        help="Maximum allowed date delta in days. Default: 3.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of duplicate groups per resolve request. Default: 50.",
    )
    parser.add_argument(
        "--max-groups",
        type=int,
        default=None,
        help="Analyze at most this many duplicate groups, for testing.",
    )
    parser.add_argument(
        "--list-actions",
        action="store_true",
        help="Print planned keep/trash actions.",
    )
    parser.add_argument(
        "--action-limit",
        type=int,
        default=20,
        help="Maximum planned actions to print with --list-actions. Default: 20.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size <= 0:
        print("--batch-size must be greater than 0")
        return 2
    if args.date_window_days < 0:
        print("--date-window-days must be greater than or equal to 0")
        return 2
    if args.max_groups is not None and args.max_groups <= 0:
        print("--max-groups must be greater than 0")
        return 2

    dry_run = not args.execute
    config = ConfigLoader(args.config)
    if not config.validate_immich_config():
        return 2

    immich_config = config.get_immich_config()
    settings_config = config.get_settings_config()

    headers = create_auth_headers(
        immich_config,
        settings_config["request_timeout"],
        settings_config["retry_attempts"],
    )
    if not headers:
        return 1

    client = ImmichClient(
        immich_config["base_url"],
        headers,
        settings_config["request_timeout"],
        settings_config["retry_attempts"],
    )

    print(f"Server: {immich_config['base_url'].rstrip('/')}")
    print(f"Date field: {args.date_field}")
    print(f"Date window: {args.date_window_days:g} days")
    print("Fetching duplicate groups...")

    try:
        duplicate_groups = client.get_duplicates()
    except (requests.exceptions.RequestException, json.JSONDecodeError, RuntimeError) as exc:
        print(f"Failed to fetch duplicate groups: {exc}")
        return 1

    if args.max_groups is not None:
        duplicate_groups = duplicate_groups[: args.max_groups]
        print(f"Limited to first {len(duplicate_groups)} duplicate groups")

    max_date_delta = timedelta(days=args.date_window_days)
    candidates, skipped = analyze_duplicates(duplicate_groups, max_date_delta, args.date_field)

    print_summary(len(duplicate_groups), candidates, skipped, dry_run)
    if args.list_actions:
        print_actions(candidates, max(0, args.action_limit))

    if dry_run:
        print("")
        print("Dry-run only. Re-run with --execute to apply these changes.")
        return 0

    if not candidates:
        print("")
        print("No duplicate groups matched the safe rules. Nothing to execute.")
        return 0

    if not ensure_trash_enabled(client):
        return 1

    resolve_groups = [candidate.to_resolve_group() for candidate in candidates]
    try:
        results = client.resolve_duplicates(resolve_groups, args.batch_size)
    except (requests.exceptions.RequestException, json.JSONDecodeError, RuntimeError) as exc:
        print(f"Failed to resolve duplicate groups: {exc}")
        return 1

    return 0 if print_execute_results(results) else 1


if __name__ == "__main__":
    sys.exit(main())
