# Immich Face Export Design

This document defines the target design for `export_face.py` and records the fixes needed to align it with the current Immich API, DigiKam/XMP expectations, and XML rules.

## Goals

The tool exports named face-recognition data from Immich into DigiKam-readable XMP sidecar files.

Success criteria:

- Read image assets and their face bounding boxes from Immich.
- Convert Immich face coordinates into MWG Image Region Metadata.
- Generate valid XML even when names, paths, or camera metadata contain special characters.
- Produce face regions, people keywords, ordinary Immich asset tags, and selected asset metadata that DigiKam and Immich can read reliably.
- Keep sidecar naming, output layout, errors, and progress reporting predictable.

Non-goals:

- Do not import DigiKam data back into Immich.
- Do not modify original photo files by default.
- Do not run face recognition.
- Do not treat the XMP output as a byte-for-byte replacement for every metadata field in the original media file.

## Reference Baseline

Use these references when implementing or reviewing changes:

- Immich OpenAPI: `https://raw.githubusercontent.com/immich-app/immich/main/open-api/immich-openapi-specs.json`
- Immich API docs: `https://immich.app/docs/api/`
- DigiKam metadata settings: `https://docs.digikam.org/en/setup_application/metadata_settings.html`
- DigiKam people view: `https://docs.digikam.org/en/left_sidebar/people_view.html`
- MWG Image Region Metadata: `https://onefolder.app/mwg.pdf`
- XML 1.0: `https://www.w3.org/TR/xml/`

Immich changes quickly. The implementation should avoid relying on old response shapes and should validate the current server responses defensively.

## Confirmed Immich Sidecar Import Behavior

Current Immich source reads sidecars through exiftool and merges sidecar tags over media-file tags during metadata extraction. For face import, it checks for `RegionInfo.AppliedToDimensions` and a non-empty `RegionInfo.RegionList`. Each region must have a `Name`; unnamed regions are skipped. Imported sidecar faces are written with Immich source type `Exif`, and Immich converts normalized MWG area coordinates back to pixel boxes using `AppliedToDimensions.W` and `AppliedToDimensions.H`.

For ordinary asset tags, Immich writes and reads XMP sidecar tags through `digiKam:TagsList`. Lightroom-style hierarchical subjects and IPTC keywords are fallback-compatible in Immich, but `digiKam:TagsList` is the primary field this exporter targets. The exporter also mirrors asset tags into `dc:subject` for general keyword search compatibility.

Immich sidecar discovery uses this order:

1. An already registered sidecar path, if present.
2. `originalPath + ".xmp"`, for example `IMG_0001.jpg.xmp`.
3. The original path with its extension replaced by `.xmp`, for example `IMG_0001.xmp`.

The exporter therefore defaults to `extension-xmp` naming so generated files match Immich's preferred discovery path and DigiKam's common sidecar convention.

## Current Problems

### 1. Face Data Is Read From The Wrong Shape

The current implementation assumes this structure:

```python
asset["people"][i]["faces"]
```

In the current Immich OpenAPI, `AssetResponseDto.people` is `PersonResponseDto[]`. A person object does not contain face bounding boxes. Face boxes should be fetched with:

```http
GET /faces?id=<asset_id>
```

That endpoint returns `AssetFaceResponseDto[]`. Important fields include:

- `boundingBoxX1`
- `boundingBoxY1`
- `boundingBoxX2`
- `boundingBoxY2`
- `imageWidth`
- `imageHeight`
- `person`
- `sourceType`

Stage 1 should work like this:

1. Use the search API to page through asset IDs.
2. Fetch asset metadata with `GET /assets/{id}`.
3. Fetch face boxes with `GET /faces?id=<asset_id>`.
4. Merge asset metadata and face data into the JSON export.

### 2. Search Parameters Need To Match Current Immich

The current request uses:

```json
{
  "page": 1,
  "size": 200,
  "isVisible": true
}
```

Current `MetadataSearchDto` does not include `isVisible`; it uses `visibility`. A better default request is:

```json
{
  "page": 1,
  "size": 200,
  "type": "IMAGE",
  "visibility": "timeline",
  "withPeople": true
}
```

Rationale:

- `type: "IMAGE"` avoids generating image sidecars for videos, audio, or other assets.
- `visibility: "timeline"` targets normal visible timeline photos.
- `withPeople: true` can include person summaries in search results, but it does not replace `/faces`.

Archived, hidden, or locked assets should be opt-in CLI/config options.

### 3. XMP Region Structure Should Follow MWG

The current implementation writes:

```xml
<mwg-rs:Regions>
  <rdf:Bag>
    ...
  </rdf:Bag>
</mwg-rs:Regions>
```

The target structure should be:

```xml
<mwg-rs:Regions rdf:parseType="Resource">
  <mwg-rs:AppliedToDimensions
    stDim:w="4032"
    stDim:h="3024"
    stDim:unit="pixel" />
  <mwg-rs:RegionList>
    <rdf:Bag>
      <rdf:li rdf:parseType="Resource">
        <mwg-rs:Name>Person Name</mwg-rs:Name>
        <mwg-rs:Type>Face</mwg-rs:Type>
        <mwg-rs:Area
          stArea:x="0.412500"
          stArea:y="0.328704"
          stArea:w="0.125000"
          stArea:h="0.166667"
          stArea:unit="normalized" />
      </rdf:li>
    </rdf:Bag>
  </mwg-rs:RegionList>
</mwg-rs:Regions>
```

Key points:

- `mwg-rs:Regions` is a structured property.
- `mwg-rs:AppliedToDimensions` should describe the image dimensions used by the region coordinates.
- Face entries belong under `mwg-rs:RegionList/rdf:Bag`.
- For normalized `mwg-rs:Area`, `x` and `y` are center coordinates; `w` and `h` are width and height ratios.

The current implementation also writes `mwg-rs:Regions=""` as an empty attribute on `rdf:Description`, then writes a `mwg-rs:Regions` element later. Remove the empty attribute and keep only the structured element.

### 4. Coordinate Normalization Should Use Face Dimensions

The current implementation normalizes coordinates with `exifInfo.exifImageWidth` and `exifInfo.exifImageHeight`. That is unreliable:

- EXIF dimensions can be null.
- EXIF dimensions can differ because of orientation, rotation, or derived images.
- Immich face objects already provide `imageWidth` and `imageHeight`, which are the coordinate basis for the face box.

Use this conversion:

```python
box_width = boundingBoxX2 - boundingBoxX1
box_height = boundingBoxY2 - boundingBoxY1
center_x = boundingBoxX1 + box_width / 2
center_y = boundingBoxY1 + box_height / 2

x = center_x / imageWidth
y = center_y / imageHeight
w = box_width / imageWidth
h = box_height / imageHeight
```

Implementation requirements:

- Skip and warn when `imageWidth <= 0` or `imageHeight <= 0`.
- Skip and warn when `box_width <= 0` or `box_height <= 0`.
- Clamp normalized values to `[0, 1]` before output.
- Use the same dimensions for `AppliedToDimensions` and coordinate normalization whenever possible.
- If faces on the same asset report inconsistent dimensions, warn clearly and avoid silently writing bad coordinates.

### 5. XML Must Be Built Safely

The current implementation builds XML with string concatenation. Any of these characters can break the file when they appear in names, paths, or metadata:

- `&`
- `<`
- `>`
- `"`
- `'`

Design requirements:

- Prefer `xml.etree.ElementTree` or another XML builder.
- If string generation remains, text nodes and attribute values must be escaped correctly.
- Tests must cover names like `Tom & Jerry <A>`, paths containing `&`, and camera metadata containing quotes.
- Generated XMP should be parsed back with an XML parser during local validation.

### 6. Unnamed Faces Should Not Become `Unknown`

Immich faces may have `person == null`, or a person with an empty name. The current fallback creates `Unknown`, which can pollute DigiKam with a fake person tag.

Default policy:

- Export only faces where `person.name` is non-empty.
- Count and report skipped unnamed faces.
- Add an explicit opt-in if unnamed regions are useful:

```bash
python export_face.py --include-unnamed-faces
```

That option can write unnamed regions with an empty name or a configured placeholder, but it should not be the default.

### 7. DigiKam Tag Compatibility

The minimum useful XMP output is MWG region metadata:

- `mwg-rs:Name`
- `mwg-rs:Type=Face`
- `mwg-rs:Area`

To also expose people as plain keywords, keep `dc:subject`:

```xml
<dc:subject>
  <rdf:Bag>
    <rdf:li>Person Name</rdf:li>
  </rdf:Bag>
</dc:subject>
```

For stronger DigiKam/Lightroom compatibility, optionally write:

- `digiKam:TagsList`
- `lr:hierarchicalSubject`

Make the people tag prefix configurable:

```json
{
  "xmp": {
    "people_tag_prefix": "People",
    "write_digikam_tags": true,
    "write_lightroom_hierarchical_subject": true
  }
}
```

Example tags could be `People/John Smith` or `People|John Smith`. The best separator should be confirmed with DigiKam before enabling this by default.

### 8. Preserve Asset Tags And Selected Metadata

GitHub issue #1 requested a more complete companion sidecar: remaining EXIF fields from the JSON export, ordinary Immich tags, full sidecar filenames, and people names as searchable tags. The corrected implementation should keep a stable face schema while also preserving metadata needed to rebuild useful companion sidecars.

Stage 1 should export:

- Ordinary Immich asset tags as normalized strings under `asset.tags`.
- Original tag details under `asset.tag_details` when the API returns IDs or hierarchy values.
- Asset metadata under `asset.asset_metadata.exif_info`.
- A top-level `people` index with person-level fields returned by the `/faces` person object.

Stage 2 should write:

- `digiKam:TagsList` for ordinary Immich asset tags by default.
- `dc:subject` for person names and, by default, ordinary asset tags.
- Optional `digiKam:TagsList` people tags with `people_tag_prefix`.
- Optional `lr:hierarchicalSubject` for asset and people tags.
- Selected EXIF/TIFF/Photoshop/XMP fields that are useful in companion XMP: camera make/model, lens, exposure settings, dimensions, capture date, rating, location coordinates, and location names.

The exporter should not claim to preserve every original media metadata field. It stores the source `exif_info` payload in JSON so future XMP mappings can be added without another Immich API scan.

### 9. Sidecar Naming And Output Location Must Be Explicit

DigiKam commonly supports:

- Default sidecar naming: `IMG_0001.jpg.xmp`
- Compatibility naming: `IMG_0001.xmp`

The current `filename.ext.xmp` behavior is a reasonable default. Add config for it:

```json
{
  "xmp": {
    "sidecar_naming": "extension-xmp"
  }
}
```

Supported values:

- `extension-xmp`: `photo.jpg.xmp`
- `replace-extension`: `photo.xmp`

Output location also needs clear behavior:

- If XMP files are written into a separate export directory, DigiKam will not automatically treat them as sidecars for the original photos unless the directory layout maps back to the photo library.
- If the goal is direct DigiKam or Immich ingestion, support `--write-next-to-original`, but require an explicit flag because it writes into photo directories.

### 10. Timeout And Retry Settings Must Actually Be Used

The config already contains:

- `settings.request_timeout`
- `settings.retry_attempts`

The current requests do not use them. Every HTTP request should use:

- `timeout=<request_timeout>`
- retry with backoff
- clear handling for 401/403, 404, 429, 5xx, and network errors

Introduce an `ImmichClient`:

```python
class ImmichClient:
    def search_assets(self, page: int, size: int) -> dict: ...
    def get_asset(self, asset_id: str) -> dict: ...
    def get_faces(self, asset_id: str) -> list[dict]: ...
```

This keeps API details, authentication, timeout, retry, and error handling in one place.

## Target JSON Model

Stage 1 should export a stable schema instead of raw Immich response fragments:

```json
{
  "schema_version": 3,
  "exported_at": "2026-05-21T12:00:00+08:00",
  "immich_server": "https://example.com",
  "people": [
    {
      "person_id": "...",
      "person_name": "John Smith",
      "is_hidden": false,
      "is_favorite": false,
      "birth_date": null,
      "thumbnail_path": "...",
      "updated_at": "..."
    }
  ],
  "assets": [
    {
      "asset_id": "...",
      "original_file_name": "IMG_0001.jpg",
      "original_path": "/library/2024/IMG_0001.jpg",
      "width": 4032,
      "height": 3024,
      "tags": ["Family/John", "Travel/Beijing"],
      "tag_details": [
        {
          "id": "...",
          "name": "Beijing",
          "value": "Travel/Beijing",
          "parent_id": "..."
        }
      ],
      "asset_metadata": {
        "exif_info": {
          "make": "Canon",
          "model": "EOS R5",
          "dateTimeOriginal": "2024-01-01T12:00:00+08:00",
          "latitude": 39.9,
          "longitude": 116.3,
          "rating": 5
        }
      },
      "faces": [
        {
          "face_id": "...",
          "source_type": "machine-learning",
          "person_id": "...",
          "person_name": "John Smith",
          "image_width": 4032,
          "image_height": 3024,
          "bounding_box": {
            "x1": 100,
            "y1": 120,
            "x2": 500,
            "y2": 620
          }
        }
      ]
    }
  ],
  "stats": {
    "assets_seen": 0,
    "assets_exported": 0,
    "assets_with_faces": 0,
    "assets_with_tags": 0,
    "named_faces": 0,
    "unnamed_faces": 0,
    "asset_tags": 0,
    "people": 0,
    "skipped_faces": 0
  }
}
```

With this structure, Stage 2 no longer depends on the raw Immich API response shape.

## Suggested Code Structure

```text
export_face.py
├── ConfigLoader
├── ImmichClient
│   ├── authenticate
│   ├── request
│   ├── search_assets
│   ├── get_asset
│   └── get_faces
├── FaceExportBuilder
│   ├── collect_asset_ids
│   ├── collect_asset_faces
│   └── write_json
├── XmpBuilder
│   ├── build_document
│   ├── add_subjects
│   ├── add_regions
│   └── validate_xml
└── CLI
```

Responsibilities:

- The API layer handles requests and response validation.
- The JSON export layer converts Immich responses into a stable schema.
- The XMP layer depends only on the stable JSON schema, not raw Immich responses.
- The CLI layer handles orchestration and user-facing output.

## Validation Plan

Required local tests:

1. XML validity
   - Person names with `&`, `<`, `"`, and `'`.
   - File paths containing `&`.
   - Generated XMP parses with `ElementTree.fromstring`.

2. Coordinate conversion
   - Input: `x1=10, y1=20, x2=110, y2=220, imageWidth=1000, imageHeight=1000`.
   - Expected output: `x=0.06, y=0.12, w=0.10, h=0.20`.

3. Unnamed faces
   - Skipped by default.
   - Preserved only when `--include-unnamed-faces` is enabled.

4. Empty face lists
   - Do not generate empty region sidecars.
   - Record skipped assets/faces in the summary.

5. Immich API schema mocks
   - Mock `/search/metadata` with `assets.items` and `nextPage`.
   - Mock `/assets/{id}` with basic asset fields.
   - Mock `/faces?id=<asset_id>` with face entries.

Optional integration checks:

- Import generated sidecars into DigiKam and confirm People view shows the names and boxes.
- If available, use `exiftool` or `exiv2` to read the generated XMP and confirm region metadata parses.

## Migration Steps

Recommended order:

1. Add `ImmichClient` and make timeout/retry settings active.
2. Update search parameters to current `MetadataSearchDto`.
3. Add `/faces?id=<asset_id>` fetching.
4. Upgrade Stage 1 JSON to `schema_version: 3`.
5. Rewrite XMP generation with an XML builder.
6. Normalize coordinates using face `imageWidth/imageHeight`.
7. Skip unnamed faces by default.
8. Add ordinary asset tag and selected metadata export.
9. Add unit tests and XML parse validation.
10. Update README usage and compatibility notes.

## Suggested Configuration

Target config:

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
    "write_dc_subject": true,
    "write_asset_tags": true,
    "write_asset_tags_to_dc_subject": true,
    "write_asset_metadata": true,
    "write_digikam_tags": false,
    "write_lightroom_hierarchical_subject": false,
    "people_tag_prefix": "People"
  },
  "search": {
    "asset_type": "IMAGE",
    "visibility": "timeline",
    "include_archived": false,
    "include_hidden": false,
    "include_locked": false
  }
}
```

Environment variable mappings to add:

- `OUTPUT_JSON_EXPORT_DIR`
- `XMP_SIDECAR_NAMING`
- `XMP_INCLUDE_UNNAMED_FACES`
- `XMP_WRITE_ASSET_TAGS`
- `XMP_WRITE_ASSET_TAGS_TO_DC_SUBJECT`
- `XMP_WRITE_ASSET_METADATA`

## Risks And Open Questions

- Immich `GET /faces` uses a query parameter named `id`; the docs can be easy to misread. Validate against the actual server response and give clear compatibility errors.
- The best combination of person-name `digiKam:TagsList` and `lr:hierarchicalSubject` should be confirmed with DigiKam before enabling person tags by default.
- If an Immich version returns only tag names without hierarchy values, the exporter can preserve the flat name but cannot reconstruct the hierarchy unless the tag list API is also consulted.
- If the Immich container path differs from the local DigiKam photo path, `originalPath` cannot be used directly for writing next to original photos. A path-mapping config is needed.
- If faces on one asset report inconsistent `imageWidth/imageHeight`, the script must warn and avoid silently writing bad coordinates.
