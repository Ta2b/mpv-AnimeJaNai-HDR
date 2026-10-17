#!/usr/bin/env python3
"""Portable safety/stability checks; native acceptance is qualified separately."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "native/apple"))
from coreml_manifest import normalize_generated_package


class ManifestCheck(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root / "model.mlpackage"
        (self.package / "Data/com.apple.CoreML/weights").mkdir(parents=True)
        (self.package / "Data/com.apple.CoreML/model.mlmodel").write_bytes(b"model specification")
        self.weight = self.package / "Data/com.apple.CoreML/weights/weight.bin"
        self.weight.write_bytes(b"weights")
        self.manifest = self.package / "Manifest.json"
        model, weights = str(uuid.uuid4()), str(uuid.uuid4())
        self.schema = {"fileFormatVersion": "1.0.0", "rootModelIdentifier": model, "itemInfoEntries": {
            model: {"author": "com.apple.CoreML", "description": "model", "name": "model.mlmodel", "path": "com.apple.CoreML/model.mlmodel"},
            weights: {"author": "com.apple.CoreML", "description": "weights", "name": "weights", "path": "com.apple.CoreML/weights"}}}
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.schema))

    def test_stable_across_random_ids_and_idempotent(self):
        other = self.root / "other.mlpackage"
        shutil.copytree(self.package, other)
        ids = {key: str(uuid.uuid4()) for key in self.schema["itemInfoEntries"]}
        self.schema["rootModelIdentifier"] = ids[self.schema["rootModelIdentifier"]]
        self.schema["itemInfoEntries"] = {ids[k]: v for k, v in self.schema["itemInfoEntries"].items()}
        (other / "Manifest.json").write_text(json.dumps(self.schema, indent=4))
        first = normalize_generated_package(self.package)
        self.assertEqual(first, normalize_generated_package(other))
        self.assertEqual(self.manifest.read_bytes(), (other / "Manifest.json").read_bytes())
        before = self.manifest.stat().st_mtime_ns
        self.assertEqual(first, normalize_generated_package(self.package))
        self.assertEqual(before, self.manifest.stat().st_mtime_ns)
        self.assertEqual(self.weight.read_bytes(), b"weights")
        # Same-length changed weights must invalidate every stable entry ID.
        previous_ids = set(json.loads(self.manifest.read_text())["itemInfoEntries"])
        self.weight.write_bytes(b"Weights")
        changed = normalize_generated_package(self.package)
        self.assertNotEqual(first["resources_sha256"], changed["resources_sha256"])
        self.assertTrue(previous_ids.isdisjoint(json.loads(self.manifest.read_text())["itemInfoEntries"]))

    def test_unsafe_or_unknown_manifests_are_untouched(self):
        root = self.schema["rootModelIdentifier"]
        original = json.loads(json.dumps(self.schema))
        for change in (lambda m: m.update(fileFormatVersion="2.0.0"),
                       lambda m: m.update(unknown="not understood"),
                       lambda m: m.update(rootModelIdentifier=str(uuid.uuid4())),
                       lambda m: m["itemInfoEntries"][root].update(path="../outside"),
                       lambda m: m["itemInfoEntries"][root].update(path="/absolute"),
                       lambda m: m["itemInfoEntries"][root].update(path="com.apple.CoreML/missing")):
            self.schema = json.loads(json.dumps(original)); change(self.schema); self.save()
            before = self.manifest.read_bytes()
            with self.assertRaises(ValueError):
                normalize_generated_package(self.package)
            self.assertEqual(before, self.manifest.read_bytes())
        self.schema = original; self.save()
        self.weight.unlink(); self.weight.symlink_to(self.root / "outside")
        with self.assertRaisesRegex(ValueError, "symlink"):
            normalize_generated_package(self.package)

    def test_duplicate_json_keys_are_rejected(self):
        self.manifest.write_text('{"fileFormatVersion":"1.0.0","fileFormatVersion":"1.0.0"}')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            normalize_generated_package(self.package)


if __name__ == "__main__":
    unittest.main()
