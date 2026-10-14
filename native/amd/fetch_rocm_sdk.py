#!/usr/bin/env python3
"""Extract a ROCm compile SDK locally; no package installation and no GPU execution."""
import argparse
import concurrent.futures
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request

PACKAGES = {
    "migraphx", "migraphx-dev", "hip-dev", "hip-runtime-amd", "hipcc",
    "rocm-device-libs", "rocm-llvm", "rocm-cmake", "rocm-core",
    "hsa-rocr-dev", "hsa-rocr", "comgr", "rocprofiler-register",
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if not shutil.which("dpkg-deb"):
        raise SystemExit("dpkg-deb is required (Ubuntu/Debian build host)")
    root = args.destination.resolve()
    archives = root / "archives"
    archives.mkdir(parents=True, exist_ok=True)
    base = "https://repo.radeon.com/rocm/apt/7.2/"
    with urllib.request.urlopen(base + "dists/noble/main/binary-amd64/Packages.gz", timeout=60) as response:
        index = gzip.decompress(response.read()).decode("utf-8")
    selected = []
    for block in index.split("\n\n"):
        fields = {}
        for line in block.splitlines():
            if ": " in line and not line.startswith(" "):
                key, value = line.split(": ", 1)
                fields[key] = value
        if fields.get("Package") in PACKAGES:
            selected.append({key: fields[key] for key in ("Package", "Filename", "SHA256", "Version")})
    if {p["Package"] for p in selected} != PACKAGES:
        raise SystemExit("ROCm 7.2 package index is incomplete")
    (root / "sdk-packages.json").write_text(json.dumps(selected, indent=2) + "\n")

    def fetch(package):
        remote = package["Filename"]
        if not remote.startswith("pool/") or ".." in remote.split("/"):
            raise RuntimeError("invalid SDK package path")
        archive = archives / Path(remote).name
        if not archive.exists():
            part = archive.with_suffix(".part")
            with urllib.request.urlopen(base + remote, timeout=120) as response, part.open("wb") as output:
                shutil.copyfileobj(response, output)
            part.replace(archive)
        with archive.open("rb") as data:
            digest = hashlib.file_digest(data, "sha256").hexdigest()
        if digest != package["SHA256"]:
            raise RuntimeError("SDK checksum mismatch: " + package["Package"])
        return archive

    # Download independently; extraction is sequential because packages share
    # directories and symlinks. Every exception propagates to the build job.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as workers:
        files = list(workers.map(fetch, selected))
    for archive in files:
        subprocess.run(["dpkg-deb", "-x", str(archive), str(root)], check=True)
    print(root / "opt/rocm-7.2.0")

if __name__ == "__main__":
    main()
