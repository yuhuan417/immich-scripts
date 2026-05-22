import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from export_face import (
    build_digikam_xmp,
    export_faces_to_digikam_xmp_from_json,
    normalize_asset,
    prepare_xmp_regions,
)


NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "digiKam": "http://www.digikam.org/ns/1.0/",
    "exif": "http://ns.adobe.com/exif/1.0/",
    "mwg-rs": "http://www.metadataworkinggroup.com/schemas/regions/",
    "photoshop": "http://ns.adobe.com/photoshop/1.0/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "stArea": "http://ns.adobe.com/xmp/sType/Area#",
    "stDim": "http://ns.adobe.com/xap/1.0/sType/Dimensions#",
    "tiff": "http://ns.adobe.com/tiff/1.0/",
}


def sample_asset(person_name="Tom & Jerry <A>"):
    return {
        "asset_id": "asset-1",
        "original_file_name": "photo.jpg",
        "original_path": "/library/2024/photo.jpg",
        "width": 1000,
        "height": 1000,
        "tags": ["Family/Trip", "Tagged & Escaped"],
        "asset_metadata": {
            "exif_info": {
                "make": "Fuji & Co",
                "model": "X <T>",
                "dateTimeOriginal": "2024-01-02T03:04:05+08:00",
                "latitude": 39.9,
                "longitude": 116.3,
                "city": "Beijing",
                "country": "China",
            }
        },
        "faces": [
            {
                "face_id": "face-1",
                "person_id": "person-1",
                "person_name": person_name,
                "image_width": 1000,
                "image_height": 1000,
                "bounding_box": {
                    "x1": 10,
                    "y1": 20,
                    "x2": 110,
                    "y2": 220,
                },
            }
        ],
    }


class ExportFaceXmpTests(unittest.TestCase):
    def test_xmp_escapes_special_characters_and_parses(self):
        xmp, stats = build_digikam_xmp(sample_asset())
        root = ET.fromstring(xmp)

        self.assertEqual(stats["faces_written"], 1)
        name = root.find(".//mwg-rs:Name", NS)
        subject = root.find(".//dc:subject/rdf:Bag/rdf:li", NS)

        self.assertIsNotNone(name)
        self.assertIsNotNone(subject)
        self.assertEqual(name.text, "Tom & Jerry <A>")
        self.assertEqual(subject.text, "Tom & Jerry <A>")

    def test_xmp_writes_immich_asset_tags_to_digikam_tagslist(self):
        xmp, stats = build_digikam_xmp(sample_asset("Alice"))
        root = ET.fromstring(xmp)

        tags = [node.text for node in root.findall(".//digiKam:TagsList/rdf:Seq/rdf:li", NS)]
        subjects = [node.text for node in root.findall(".//dc:subject/rdf:Bag/rdf:li", NS)]

        self.assertEqual(stats["asset_tags"], ["Family/Trip", "Tagged & Escaped"])
        self.assertIn("Family/Trip", tags)
        self.assertIn("Tagged & Escaped", tags)
        self.assertIn("Alice", subjects)
        self.assertIn("Family/Trip", subjects)

    def test_xmp_writes_exported_asset_metadata(self):
        xmp, stats = build_digikam_xmp(sample_asset("Alice"))
        root = ET.fromstring(xmp)

        self.assertGreater(stats["metadata_fields_written"], 0)
        self.assertEqual(root.find(".//tiff:Make", NS).text, "Fuji & Co")
        self.assertEqual(root.find(".//tiff:Model", NS).text, "X <T>")
        self.assertEqual(root.find(".//exif:DateTimeOriginal", NS).text, "2024-01-02T03:04:05+08:00")
        self.assertEqual(root.find(".//photoshop:City", NS).text, "Beijing")

    def test_xmp_contains_immich_importable_region_info_shape(self):
        xmp, _ = build_digikam_xmp(sample_asset("Alice"))
        root = ET.fromstring(xmp)

        applied = root.find(".//mwg-rs:Regions/mwg-rs:AppliedToDimensions", NS)
        region = root.find(".//mwg-rs:Regions/mwg-rs:RegionList/rdf:Bag/rdf:li", NS)
        area = root.find(".//mwg-rs:Area", NS)

        self.assertIsNotNone(applied)
        self.assertIsNotNone(region)
        self.assertIsNotNone(area)
        self.assertEqual(applied.find("stDim:w", NS).text, "1000")
        self.assertEqual(applied.find("stDim:h", NS).text, "1000")
        self.assertEqual(applied.find("stDim:unit", NS).text, "pixel")
        self.assertEqual(region.find("mwg-rs:Name", NS).text, "Alice")
        self.assertEqual(region.find("mwg-rs:Type", NS).text, "Face")
        self.assertEqual(area.find("stArea:unit", NS).text, "normalized")

    def test_coordinate_conversion_uses_face_dimensions(self):
        regions, stats = prepare_xmp_regions(sample_asset("Alice"), {})

        self.assertEqual(stats["dimensions"], (1000, 1000))
        self.assertEqual(len(regions), 1)
        self.assertAlmostEqual(regions[0]["x"], 0.06)
        self.assertAlmostEqual(regions[0]["y"], 0.12)
        self.assertAlmostEqual(regions[0]["w"], 0.10)
        self.assertAlmostEqual(regions[0]["h"], 0.20)

    def test_unnamed_faces_are_skipped_by_default(self):
        asset = sample_asset("")
        asset["tags"] = []
        asset["asset_metadata"] = {"exif_info": {}}
        xmp, stats = build_digikam_xmp(asset)

        self.assertEqual(xmp, "")
        self.assertEqual(stats["skipped_unnamed"], 1)

    def test_tags_only_asset_still_writes_sidecar(self):
        asset = sample_asset("")
        asset["faces"] = []
        asset["tags"] = ["Archive/Scans"]
        asset["asset_metadata"] = {"exif_info": {}}

        xmp, stats = build_digikam_xmp(asset)
        root = ET.fromstring(xmp)
        tags = [node.text for node in root.findall(".//digiKam:TagsList/rdf:Seq/rdf:li", NS)]

        self.assertEqual(stats["faces_written"], 0)
        self.assertEqual(tags, ["Archive/Scans"])
        self.assertIsNone(root.find(".//mwg-rs:Regions", NS))

    def test_normalize_asset_exports_tags_exif_and_face_people(self):
        asset = {
            "id": "asset-1",
            "originalFileName": "photo.jpg",
            "originalPath": "/library/photo.jpg",
            "width": 2000,
            "height": 1000,
            "tags": [{"id": "tag-1", "name": "Trip", "value": "Places/Trip"}],
            "exifInfo": {"make": "Canon", "tags": ["Fallback/Tag"]},
        }
        faces = [
            {
                "id": "face-1",
                "sourceType": "machine-learning",
                "imageWidth": 2000,
                "imageHeight": 1000,
                "boundingBoxX1": 100,
                "boundingBoxY1": 200,
                "boundingBoxX2": 300,
                "boundingBoxY2": 600,
                "person": {"id": "person-1", "name": "Alice"},
            }
        ]

        normalized = normalize_asset(asset, faces)

        self.assertEqual(normalized["tags"], ["Places/Trip", "Fallback/Tag"])
        self.assertEqual(normalized["tag_details"][0]["id"], "tag-1")
        self.assertEqual(normalized["asset_metadata"]["exif_info"]["make"], "Canon")
        self.assertEqual(normalized["faces"][0]["person_name"], "Alice")

    def test_stage2_writes_default_immich_sidecar_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "faces.json"
            out_dir = Path(temp_dir) / "xmp"
            export_data = {
                "schema_version": 2,
                "assets": [sample_asset("Alice")],
            }
            json_path.write_text(json.dumps(export_data), encoding="utf-8")

            success = export_faces_to_digikam_xmp_from_json(str(json_path), str(out_dir))

            self.assertTrue(success)
            sidecar = out_dir / "library" / "2024" / "photo.jpg.xmp"
            self.assertTrue(sidecar.exists())
            ET.fromstring(sidecar.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
