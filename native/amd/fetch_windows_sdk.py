#!/usr/bin/env python3
"""Extract a pinned Windows AMD SDK; compilation only, no installation/inference.

HIP/ROCm wheels are from AMD. MIGraphX DLLs/import libraries are the explicitly
identified community Windows port, not an official AMD binary distribution.
--runtime adds the RX 9070 XT math libraries/data for an optional portable pack.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

VERSION = "10.1.0a20260822"
WHEELS = {
    "core": "6211f8b693b900fef3a2d4facb3ff995077acfa782aab89db21cb0874449a690",
    "devel": "fbe70f3606bd86c5684a1d1e2830bd1865ea0ed92ee4e7a2165bb5c038b927e9",
    "libraries": "4210ffe35dbcbe4aa5038364ee9321cc2cb3f27354d55d0f925c24a140da2728",
    "device_gfx1201": "2c05fb55363ca96061937cda4583534ba4e123796a867ec6018607e42bbf3b28",
}
MIG_VERSION = "v10.1.0a20260822"
MIG_URL = f"https://github.com/lc700x/MIGraphX-Windows/releases/download/{MIG_VERSION}/build.7z"
MIG_SHA = "b2a96f35fcc41cc504869583d51f5c5cd475cad5093f602e0ed67fbca5b220ad"
API_REF = "95672916ed289d4be9d230a9be732e1bbad97e8c"  # upstream rocm-10.1, MIGraphX 2.18
API_BASE = f"https://raw.githubusercontent.com/ROCm/AMDMIGraphX/{API_REF}/"
API_FILES = {
    "src/api/include/migraphx/migraphx.h": (
        "include/migraphx/migraphx.h", "1026dc365e65a8133bf19c78a902d313b66d61f56311f7d20f5b09070b6c9f6d"),
    "LICENSE": ("share/aji-amd/MIGraphX-LICENSE.txt",
                "2282fd4f9d4acde1c5ab41a3d189752fd0af1048aec181519a903a0c8da8de53"),
}
NOTICES = {
    "abseil": ("abseil/abseil-cpp/20250512.0/LICENSE", "c79a7fea0e3cac04cd43f20e7b648e5a0ff8fa5344e644b0ee09ca1162b62747"),
    "protobuf": ("protocolbuffers/protobuf/v30.0/LICENSE", "6e5e117324afd944dcf67f36cf329843bc1a92229a8cd9bb573d7a83130fea7d"),
    "json": ("nlohmann/json/v3.8.0/LICENSE.MIT", "50be9457e5c9faaba5e60d9c73f8eabe9e0737a2d9c3e58357d856661862c18e"),
    "msgpack": ("msgpack/msgpack-c/cpp-3.3.0/COPYING", "664550b43996452a5a2c7471bb0ff77185a58c69ccafa60f983dc4c162e1ee22"),
    "CK": ("ROCm/composable_kernel/ad0db05b040bacda751c65c705261b8a0a7ed25d/LICENSE", "20f3b83dfda01bd18d285e0edbb9d044be6dde04cdf76a1ec18d9fc7127936bf"),
    "rocmlir": ("ROCm/rocmlirTriton/8e5fabb7ff85c1e59a1b1749015379e32d9bf1ae/LICENSE", "94b301bb652ae351f5941655bf533f1a136300ad1396be7452c8a04ff2c91374"),
}


def fetch(url, path, digest):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_suffix(path.suffix + ".part")
        with urllib.request.urlopen(url, timeout=120) as source, temporary.open("wb") as out:
            shutil.copyfileobj(source, out)
        temporary.replace(path)
    with path.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != digest:
        raise RuntimeError(f"Checksum mismatch: {path.name}")
    return path


def sdk_relative(name):
    # The devel tar uses links into the core/library wheels. Merge their regular
    # files into one portable prefix instead of requiring Windows symlink rights.
    parts = name.replace("\\", "/").split("/")
    if not parts[0].startswith("_rocm_sdk_") or ".." in parts:
        return None
    if len(parts) < 2 or any(":" in p for p in parts):
        return None
    return Path(*parts[1:])


def extract_wheel(archive, destination):
    with zipfile.ZipFile(archive) as wheel:
        for entry in wheel.infolist():
            if entry.is_dir():
                continue
            if entry.filename.endswith("/_devel.tar"):
                with wheel.open(entry) as stream, tarfile.open(fileobj=stream, mode="r|") as tar:
                    for member in tar:
                        relative = sdk_relative(member.name)
                        if relative is None or not member.isfile():
                            continue
                        path = destination / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with tar.extractfile(member) as data, path.open("wb") as out:
                            shutil.copyfileobj(data, out)
            else:
                relative = sdk_relative(entry.filename)
                if relative is None:
                    continue
                path = destination / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                with wheel.open(entry) as data, path.open("wb") as out:
                    shutil.copyfileobj(data, out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--archives", type=Path)
    parser.add_argument("--runtime", action="store_true")
    args = parser.parse_args()
    root = args.destination.resolve()
    cache = args.archives or root.parent / "windows-amd-archives"
    entries = {}
    for part, digest in WHEELS.items():
        if not args.runtime and part not in ("core", "devel"):
            continue
        name = f"rocm_sdk_{part}-{VERSION}-py3-none-win_amd64.whl"
        entries[name] = ("https://rocm.nightlies.amd.com/whl-multi-arch/" + name, digest)
    entries["migraphx-build.7z"] = (MIG_URL, MIG_SHA)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as workers:
        futures = {name: workers.submit(fetch, url, cache / name, digest)
                   for name, (url, digest) in entries.items()}
        files = {name: future.result() for name, future in futures.items()}
    for name, archive in files.items():
        if name.endswith(".whl"):
            extract_wheel(archive, root)
    seven = shutil.which("7z") or shutil.which("7zz")
    if not seven:
        raise SystemExit("7z/7zz is required to extract the MIGraphX Windows import libraries")
    # Exclude the port's unrelated ORT binaries: the existing DirectML runtime
    # remains the metadata API, and no conflicting ORT DLL is distributed.
    subprocess.run([seven, "x", "-y", f"-o{root}", str(files["migraphx-build.7z"]),
                    "bin/*", "lib/*"], check=True, stdout=subprocess.DEVNULL)
    for source, (target, digest) in API_FILES.items():
        archive = fetch(API_BASE + source, cache / Path(target).name, digest)
        path = root / target
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(archive, path)
    for name, (source, digest) in NOTICES.items():
        license_file = fetch("https://raw.githubusercontent.com/" + source, cache / (name + "-LICENSE.txt"), digest)
        shutil.copyfile(license_file, root / "share/aji-amd" / license_file.name)
    # Equivalent to GenerateExportHeader's Windows consumer declaration.
    (root / "include/migraphx/api").mkdir(parents=True, exist_ok=True)
    (root / "include/migraphx/api/export.h").write_text(
        "#pragma once\n#define MIGRAPHX_C_EXPORT __declspec(dllimport)\n", encoding="utf-8")
    # The C header includes config.h but uses none of the C++ build's feature
    # macros. This consumer SDK deliberately exposes the C API only.
    (root / "include/migraphx/config.h").write_text(
        "#pragma once\n// C API consumer; no C++ MIGraphX configuration exposed.\n", encoding="utf-8")
    manifest = {"rocm_version": VERSION, "migraphx_version": "2.18.0",
                "migraphx_binary_source": "lc700x/MIGraphX-Windows (community port)",
                "migraphx_header_ref": API_REF, "runtime_gfx1201": args.runtime,
                "archives": [{"file": name, "url": url, "sha256": sha}
                             for name, (url, sha) in entries.items()]}
    (root / "AMD-SDK-PROVENANCE.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(root)


if __name__ == "__main__":
    main()
