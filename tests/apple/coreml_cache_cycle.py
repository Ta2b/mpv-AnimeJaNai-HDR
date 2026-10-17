#!/usr/bin/env python3
"""One native Core ML cache cycle, using private copies and synthetic RGB.

No FPS comparison. Each case resolves a distinct cache/fidelity uncertainty.
The work directory must not exist: no installed model or cache is ever modified.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "native/apple"))
from coreml_manifest import normalize_generated_package


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("models", "probe", "identity", "work"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    work = args.work.resolve()
    source = args.models.resolve()
    model = next(source.glob("*Sharp1_Performance*.mlpackage")).stem
    donor = next(source.glob("*V3.1_Performance*.mlpackage")).stem
    original, normalized = work / "original", work / "normalized"
    original.mkdir(); normalized.mkdir()
    for name in (model, donor):
        shutil.copytree(source / (name + ".mlpackage"), original / (name + ".mlpackage"))
        shutil.copy2(source / (name + ".mlpatch"), original / (name + ".mlpatch"))
    shutil.copytree(original, normalized, dirs_exist_ok=True)
    package = normalized / (model + ".mlpackage")
    resources_before = {p.relative_to(package).as_posix(): sha(p) for p in package.rglob("*")
                        if p.is_file() and p.name != "Manifest.json"}
    recipe = normalize_generated_package(package)
    assert resources_before == {p.relative_to(package).as_posix(): sha(p) for p in package.rglob("*")
                                if p.is_file() and p.name != "Manifest.json"}
    cache = work / "cache"
    results = {"source": os.environ.get("GITHUB_SHA"), "normalization": recipe, "cases": {}}

    def tag(models, name=model):
        return subprocess.check_output([str(args.identity.resolve()), str(models), name], text=True).strip()

    def compiled(content, name=model):
        matching = next(e for e in results["cases"].values() if e["content_tag"] == content and e["model"] == name)
        if matching.get("generation"):
            return cache / "native/coreml-tx1" / matching["program_key"] / matching["generation"] / "model.mlmodelc"
        suffix = "p3-" + matching["program_key"] if matching["program_key"] else content
        return cache / "native" / (name + "-256x256-" + suffix) / "model.mlmodelc"

    def run(label, models, name=model, miss=True, fails=False):
        output = work / (label + ".rgb")
        process = subprocess.run([str(args.probe.resolve()), str(models), name, str(cache), str(output)],
                                 env={**os.environ, "AJI_COREML_NO_PLAN": "1"}, capture_output=True, text=True)
        (work / (label + ".log")).write_text(process.stdout + process.stderr)
        program_key = re.search(r"Core ML cache identity: p3-([0-9a-f]{64})", process.stderr)
        generation = re.search(r"Core ML committed cache: [0-9a-f]{64} generation (data-[0-9-]+)", process.stderr)
        evidence = {"generation": generation.group(1) if generation else None, "returncode": process.returncode, "cache_miss": "compiled cache miss:" in process.stderr,
                    "content_tag": tag(models, name), "model": name,
                    "program_key": program_key.group(1) if program_key else None}
        results["cases"][label] = evidence
        if fails:
            assert process.returncode != 0 and any(message in process.stderr for message in
                ("cache cleared, try again", "invalid commit retired, data preserved")), process.stderr
        else:
            assert process.returncode == 0, process.stderr
            assert evidence["cache_miss"] == miss, evidence
            assert output.stat().st_size == 512 * 512 * 3
            evidence["output_sha256"] = sha(output)
        return output

    old_tag, stable_tag = tag(original), tag(normalized)
    assert old_tag != stable_tag  # One intentional migration from random IDs.
    old = run("original-cold", original)
    old_compiled = compiled(old_tag)
    inode = old_compiled.stat().st_ino
    hit = run("original-hit", original, miss=False)
    assert sha(old) == sha(hit) and old_compiled.stat().st_ino == inode
    fixed = run("normalized-cold", normalized)
    assert sha(old) == sha(fixed), "normalizing IDs changed the RGB output"
    # A separately copied, identically normalized export must reuse the cache.
    reexport = work / "reexport"
    shutil.copytree(normalized, reexport)
    assert normalize_generated_package(reexport / (model + ".mlpackage")) == recipe
    stable_compiled = compiled(stable_tag)
    inode = stable_compiled.stat().st_ino
    hit = run("identical-reexport-hit", reexport, miss=False)
    assert sha(fixed) == sha(hit) and stable_compiled.stat().st_ino == inode

    # Valid weights-only replacement: both released models use byte-identical
    # programs/tables, so the donor blob has the same layout and offsets.
    spec = "Data/com.apple.CoreML/model.mlmodel"
    blob = "Data/com.apple.CoreML/weights/weight.bin"
    donor_package = normalized / (donor + ".mlpackage")
    assert (package / spec).read_bytes() == (donor_package / spec).read_bytes()
    assert (normalized / (model + ".mlpatch")).read_bytes() == (normalized / (donor + ".mlpatch")).read_bytes()
    assert (package / blob).stat().st_size == (donor_package / blob).stat().st_size
    assert sha(package / blob) != sha(donor_package / blob)
    manifest_before = (package / "Manifest.json").read_bytes()
    shutil.copyfile(donor_package / blob, package / blob)
    assert manifest_before == (package / "Manifest.json").read_bytes()
    changed_tag = tag(normalized)
    assert changed_tag not in (old_tag, stable_tag)
    changed = run("weights-only-rebuild", normalized)
    reference = run("donor-reference", normalized, donor)
    assert sha(changed) == sha(reference) and sha(changed) != sha(fixed), "stale or incorrect weights"
    damaged = compiled(changed_tag)
    shutil.rmtree(damaged); damaged.mkdir()  # A present, invalid compiled cache.
    run("corrupt-cache-diagnostic", normalized, fails=True)
    if results["cases"]["corrupt-cache-diagnostic"].get("generation"):
        assert damaged.parent.exists() and not (damaged.parent.parent/"current").exists(), "invalid commit not retired or generation erased"
    else:
        assert not damaged.parent.exists(), "the failed legacy entry was not cleared"
    recovered = run("retry-rebuild", normalized)
    assert sha(recovered) == sha(changed)
    assert old_compiled.is_dir() and stable_compiled.is_dir(), "unrelated old entries were removed"
    results.update(passed=True, pixels_exact_after_normalization=True, changed_weights_match_donor=True,
                   old_entries_preserved=True, scope="macOS native Core ML CPU, 256x256 RGB; no GPU/ANE/FPS claim")
    (work / "receipt.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
