#!/usr/bin/env python3
"""Stable IDs for newly generated Core ML packages; never run on installed models.

Only Manifest 1.0.0 is understood. Model/weight bytes stay untouched and remain
part of the runtime content identity. Changing any resource changes the IDs too.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import uuid

RECIPE = "animejanai-coreml-manifest-v1"
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/Ta2b/mpv-AnimeJaNai-HDR/" + RECIPE)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key: " + key)
        result[key] = value
    return result


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def normalize_generated_package(package):
    """Atomically normalize a converter-owned package, returning its recipe/digest.

    Validate the complete package before writing. Refuse unknown schemas, links
    and ambiguous paths instead of guessing how to rewrite their references.
    """
    package = Path(package)
    if package.is_symlink() or not package.is_dir():
        raise ValueError("expected a generated package directory")
    paths = sorted(package.rglob("*"), key=lambda p: p.relative_to(package).as_posix())
    if any(p.is_symlink() or not (p.is_file() or p.is_dir()) for p in paths):
        raise ValueError("package contains a symlink or special file")
    manifest_path = package / "Manifest.json"
    original = manifest_path.read_bytes()
    manifest = json.loads(original, object_pairs_hook=_unique_object)
    if (not isinstance(manifest, dict)
            or set(manifest) != {"fileFormatVersion", "itemInfoEntries", "rootModelIdentifier"}
            or manifest["fileFormatVersion"] != "1.0.0"):
        raise ValueError("unsupported Core ML manifest schema")
    entries = manifest["itemInfoEntries"]
    root = manifest["rootModelIdentifier"]
    if not isinstance(entries, dict) or not entries or not isinstance(root, str) or root not in entries:
        raise ValueError("missing manifest root")
    seen_paths = set()
    for identifier, entry in entries.items():
        if str(uuid.UUID(identifier)).upper() != identifier.upper():
            raise ValueError("invalid manifest UUID")
        if (not isinstance(entry, dict) or set(entry) != {"author", "description", "name", "path"}
                or any(not isinstance(v, str) or not v for v in entry.values())):
            raise ValueError("unsupported manifest entry")
        path = PurePosixPath(entry["path"])
        if (path.is_absolute() or ".." in path.parts or path.as_posix() != entry["path"]
                or path.as_posix() == "." or "\\" in entry["path"]
                or any(ord(c) < 32 for c in entry["path"]) or entry["path"] in seen_paths):
            raise ValueError("unsafe or duplicate manifest path")
        seen_paths.add(entry["path"])
        target = package / "Data" / path
        if not target.exists():
            raise ValueError("manifest entry is missing: " + entry["path"])
        if identifier == root and (not target.is_file() or target.suffix != ".mlmodel"):
            raise ValueError("manifest root is not a model specification")

    digest = hashlib.sha256((RECIPE + "\0resources\0").encode())
    resources = [p for p in paths if p.is_file() and p != manifest_path]
    for path in resources:
        relative = path.relative_to(package).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big")); digest.update(relative)
        digest.update(path.stat().st_size.to_bytes(8, "big"))
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    resource_sha256 = digest.hexdigest()
    replacements = {old: str(uuid.uuid5(NAMESPACE, resource_sha256 + "\0" + _canonical(entry))).upper()
                    for old, entry in entries.items()}
    if len(set(replacements.values())) != len(entries):
        raise ValueError("stable UUID collision")
    manifest["itemInfoEntries"] = {replacements[old]: entry for old, entry in entries.items()}
    manifest["rootModelIdentifier"] = replacements[root]
    normalized = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if normalized != original:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=package, prefix=".manifest-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(normalized)
            os.chmod(temporary, manifest_path.stat().st_mode & 0o777)
            os.replace(temporary, manifest_path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {"recipe": RECIPE, "resources_sha256": resource_sha256,
            "manifest_sha256": hashlib.sha256(normalized).hexdigest()}
