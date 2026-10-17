#!/usr/bin/env python3
"""Exercise the prepared recipe's real reset helper, without cross-compiling."""
from pathlib import Path
import subprocess
import sys
import tempfile

recipe = Path(sys.argv[1]).resolve()


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, **kwargs).strip()


with tempfile.TemporaryDirectory(prefix="aji-winbuild-reset-") as temporary:
    root = Path(temporary)
    upstream = root / "upstream"
    upstream.mkdir()
    run("git", "init", "-b", "main", str(upstream))
    run("git", "-C", str(upstream), "config", "user.email", "fixture@example.invalid")
    run("git", "-C", str(upstream), "config", "user.name", "Fixture")
    for value in ("pinned", "new upstream"):
        (upstream / "source.txt").write_text(value)
        run("git", "-C", str(upstream), "add", "source.txt")
        run("git", "-C", str(upstream), "commit", "-m", value)
        if value == "pinned":
            pinned = run("git", "-C", str(upstream), "rev-parse", "HEAD")
    latest = run("git", "-C", str(upstream), "rev-parse", "HEAD")
    projects = []
    for name, tag in (("pinned", pinned), ("tracking", "main")):
        source = root / name
        run("git", "clone", str(upstream), str(source))
        if name == "pinned":
            run("git", "-C", str(source), "checkout", "--detach", pinned)
        else:
            run("git", "-C", str(source), "reset", "--hard", pinned)
        projects.append(f'''
ExternalProject_Add({name}
  GIT_REPOSITORY "{upstream}" GIT_TAG {tag} SOURCE_DIR "{source}"
  DOWNLOAD_COMMAND "" UPDATE_COMMAND "" CONFIGURE_COMMAND "" BUILD_COMMAND "" INSTALL_COMMAND "")
force_rebuild_git({name})
get_property(stamp TARGET {name} PROPERTY _EP_STAMP_DIR)
file(WRITE "${{stamp}}/HEAD" "{pinned}\\n")
file(WRITE "${{stamp}}/{name}-patch" "")
file(WRITE "${{CMAKE_BINARY_DIR}}/{name}-stamp.txt" "${{stamp}}")
''')
    (root / "CMakeLists.txt").write_text(f'''cmake_minimum_required(VERSION 3.20)
project(reset_fixture NONE)
include(ExternalProject)
include("{recipe}/cmake/custom_steps.cmake")
''' + "".join(projects))
    run("cmake", "-S", str(root), "-B", str(root / "build"))
    for name, expected, content in (("pinned", pinned, "pinned"), ("tracking", latest, "new upstream")):
        stamp = Path((root / "build" / (name + "-stamp.txt")).read_text())
        source = root / name
        (source / "source.txt").write_text("uncommitted build patch")
        run("bash", str(stamp / "reset_head.sh"))
        assert run("git", "-C", str(source), "rev-parse", "HEAD") == expected
        assert (source / "source.txt").read_text() == content
        if name == "pinned":
            assert run("git", "-C", str(source), "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
            # Mismatched stamp exercises the helper's other branch, too.
            (stamp / "HEAD").write_text(latest + "\n")
            run("bash", str(stamp / "reset_head.sh"))
            assert run("git", "-C", str(source), "rev-parse", "HEAD") == pinned
            assert (stamp / "HEAD").read_text().strip() == pinned
    print("PASS: detached commit stays pinned; tracking branch follows upstream; both reset paths work")
