import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from export_face import (
    build_digikam_xmp,
    export_faces_to_digikam_xmp_from_json,
    prepare_xmp_regions,
)


NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "mwg-rs": "http://www.metadataworkinggroup.com/schemas/regions/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "stArea": "http://ns.adobe.com/xmp/sType/Area#",
    "stDim": "http://ns.adobe.com/xap/1.0/sType/Dimensions#",
}


def sample_asset(person_name="Tom & Jerry <A>"):
    return {
        "asset_id": "asset-1",
        "original_file_name": "photo.jpg",
        "original_path": "/library/2024/photo.jpg",
        "width": 1000,
        "height": 1000,
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
        xmp, stats = build_digikam_xmp(sample_asset(""))

        self.assertEqual(xmp, "")
        self.assertEqual(stats["skipped_unnamed"], 1)

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
