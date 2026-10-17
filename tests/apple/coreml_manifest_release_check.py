#!/usr/bin/env python3
"""Compare actual .86/.87 model resources on private copies (stdlib + identity CLI)."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "native/apple"))
from coreml_manifest import normalize_generated_package


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("previous_zip", "current_zip", "identity", "work"):
        parser.add_argument("--" + key.replace("_", "-"), type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    roots = [args.work / label for label in ("previous", "current")]
    prefix = "mpv AnimeJaNai.app/Contents/Resources/animejanai/onnx/"
    for archive_path, root in zip((args.previous_zip, args.current_zip), roots):
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if member.is_dir() or not member.filename.startswith(prefix):
                    continue
                relative = Path(member.filename[len(prefix):])
                assert not relative.is_absolute() and ".." not in relative.parts
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
    before = [snapshot(root) for root in roots]
    assert before[0].keys() == before[1].keys()
    differences = [p for p in before[0] if before[0][p] != before[1][p]]
    assert len(differences) == 4 and all(p.endswith(".mlpackage/Manifest.json") for p in differences), differences
    names = sorted(p.stem for p in roots[0].glob("*.mlpackage"))
    assert len(names) == 4

    def tag(root, name):
        return subprocess.check_output([str(args.identity.resolve()), str(root), name], text=True).strip()

    old_tags = [{name: tag(root, name) for name in names} for root in roots]
    recipes = {}
    for index, root in enumerate(roots):
        for name in names:
            package = root / (name + ".mlpackage")
            recipe = normalize_generated_package(package)
            manifest = package / "Manifest.json"
            mtime = manifest.stat().st_mtime_ns
            assert recipe == normalize_generated_package(package) and mtime == manifest.stat().st_mtime_ns
            recipes[str(index) + "/" + name] = recipe
        after = snapshot(root)
        assert all(before[index][p] == after[p] for p in after if not p.endswith(".mlpackage/Manifest.json"))
    assert snapshot(roots[0]) == snapshot(roots[1]), "identical model resources did not converge"
    stable_tags = {name: tag(roots[0], name) for name in names}
    assert stable_tags == {name: tag(roots[1], name) for name in names}
    assert all(stable_tags[name] != old_tags[index][name] for index in range(2) for name in names)
    sharp = next(name for name in names if "Sharp1_Performance" in name)
    donor = next(name for name in names if "V3.1_Performance" in name)
    package = roots[1] / (sharp + ".mlpackage")
    old_ids = set(json.loads((package / "Manifest.json").read_text())["itemInfoEntries"])
    blob = "Data/com.apple.CoreML/weights/weight.bin"
    shutil.copyfile(roots[1] / (donor + ".mlpackage") / blob, package / blob)
    changed_before_normalization = tag(roots[1], sharp)
    assert changed_before_normalization != stable_tags[sharp]
    normalize_generated_package(package)
    assert old_ids.isdisjoint(json.loads((package / "Manifest.json").read_text())["itemInfoEntries"])
    changed_after_normalization = tag(roots[1], sharp)
    assert changed_after_normalization not in (stable_tags[sharp], changed_before_normalization)
    receipt = {"passed": True, "resource_count_per_release": len(before[0]), "original_differences": differences,
               "old_tags": old_tags, "stable_tags": stable_tags, "recipes": recipes,
               "all_resources_exact_after_normalization": True, "non_manifest_resources_unchanged": True,
               "valid_weights_only_replacement_changes_tag_and_ids": True,
               "scope": "portable content identity; no Apple API or FPS claim"}
    (args.work / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in ("passed", "resource_count_per_release", "non_manifest_resources_unchanged")}))


if __name__ == "__main__":
    main()
