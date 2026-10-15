#!/usr/bin/env python3
"""Called only under the repository-wide release-latest concurrency lock."""
import json
import os
import re
import subprocess
import sys


def version(tag):
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", tag):
        raise ValueError(f"Not a stable AnimeJaNai version: {tag!r}")
    return tuple(map(int, tag.split(".")))


def main():
    candidate = sys.argv[1]
    number = version(candidate)
    repo = os.environ["GITHUB_REPOSITORY"]
    releases = json.loads(subprocess.check_output([
        "gh", "release", "list", "--repo", repo, "--limit", "1000",
        "--json", "tagName,isLatest,isDraft,isPrerelease",
    ], text=True))
    own = next((r for r in releases if r["tagName"] == candidate), None)
    if own is None or own["isDraft"] or own["isPrerelease"]:
        raise ValueError("Candidate release is absent or is not published and stable")
    latest = [r for r in releases if r["isLatest"]]
    if len(latest) > 1 or (not latest and len(releases) >= 1000):
        raise ValueError("Cannot establish the current latest release")
    if latest and version(latest[0]["tagName"]) >= number:
        print(f"Keep latest {latest[0]['tagName']}; completed platform of {candidate}")
        return
    subprocess.run(["gh", "release", "edit", candidate, "--repo", repo, "--latest"], check=True)
    print(f"Promoted {candidate}")


if __name__ == "__main__":
    main()
