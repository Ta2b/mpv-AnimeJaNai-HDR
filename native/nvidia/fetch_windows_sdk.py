#!/usr/bin/env python3
"""Extract NVIDIA's Windows CUDA/TensorRT build dependencies; never run inference."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import shutil
import urllib.request
import zipfile


def fetch(url, destination, expected):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        part = destination.with_suffix(destination.suffix + ".part")
        with urllib.request.urlopen(url, timeout=120) as source, part.open("wb") as out:
            shutil.copyfileobj(source, out)
        part.replace(destination)
    with destination.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != expected:
            raise RuntimeError("NVIDIA SDK checksum mismatch: " + destination.name)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    root = args.destination.resolve()
    cache = root / "archives"
    program = (Path(__file__).resolve().parents[2] / "BuildMpvUpscale2xAnimeJaNai/Program.cs").read_text()
    def pin(name):
        match = re.search(r'const string ' + name + r'\s*=\s*"([^"]+)"', program)
        if not match:
            raise RuntimeError("Missing assembler pin: " + name)
        return match[1]
    trt_version, trt_cuda = pin("TrtVersion"), pin("TrtCudaVersion")
    trt_name = f"TensorRT-Enterprise-{trt_version}-Windows-amd64-cuda-{trt_cuda}-Release-external.zip"
    short_version = ".".join(trt_version.split(".")[:3])
    trt_url = f"https://developer.nvidia.com/downloads/compute/machine-learning/tensorrt/{short_version}/zip/{trt_name}"
    # Component hashes are NVIDIA's, from the immutable CUDA redist release.
    manifest_url = "https://developer.download.nvidia.com/compute/cuda/redist/redistrib_13.4.1.json"
    with urllib.request.urlopen(manifest_url, timeout=60) as response:
        manifest = json.load(response)
    components = {name: manifest[name]["windows-x86_64"]
                  for name in ("cuda_nvcc", "cuda_crt", "cuda_cudart", "libnvvm", "cccl")}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as workers:
        futures = {name: workers.submit(fetch,
            "https://developer.download.nvidia.com/compute/cuda/redist/" + entry["relative_path"],
            cache / Path(entry["relative_path"]).name, entry["sha256"])
            for name, entry in components.items()}
        trt = workers.submit(fetch, trt_url, cache / trt_name, pin("TrtSha256Win"))
        archives = {name: future.result() for name, future in futures.items()}
        trt_archive = trt.result()
    for name, archive in archives.items():
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                if entry.is_dir(): continue
                parts = entry.filename.split("/")[1:]
                if not parts or ".." in parts: continue
                relative = Path(*parts)
                if relative.name.upper().startswith("LICENSE"):
                    relative = Path("share/aji-nvidia") / (name + "-" + relative.name)
                path = root / "cuda" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                with source.open(entry) as data, path.open("wb") as out:
                    shutil.copyfileobj(data, out)
    with zipfile.ZipFile(trt_archive) as source:
        for entry in source.infolist():
            name = Path(entry.filename).name
            if entry.is_dir(): continue
            if "/include/" in entry.filename:
                relative = Path("include") / entry.filename.split("/include/", 1)[1]
            elif name == "nvinfer_11.lib":
                relative = Path(name)
            elif name == "Acknowledgements.txt":
                relative = Path(name)
            else: continue
            path = root / "trt" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as data, path.open("wb") as out:
                shutil.copyfileobj(data, out)
    for path in (root / "trt/nvinfer_11.lib", root / "cuda/bin/nvcc.exe",
                 root / "cuda/lib/x64/cuda.lib"):
        if not path.is_file(): raise RuntimeError("Incomplete Windows NVIDIA SDK: " + str(path))
    provenance = {"cuda_manifest": manifest_url, "components": components,
                  "tensorrt": {"url": trt_url, "sha256": pin("TrtSha256Win")}}
    (root / "NVIDIA-SDK-PROVENANCE.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(root)


if __name__ == "__main__":
    main()
