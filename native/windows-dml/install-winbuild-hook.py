#!/usr/bin/env python3
"""Install the exact-pair preparation step into an existing winbuild checkout."""
from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1]).resolve()
recipe = root/'packages/mpv.cmake'
text = recipe.read_text()
if 'ExternalProject_Add(mpv' not in text or 'GIT_REPOSITORY https://github.com/' not in text:
    raise SystemExit('Unknown mpv-winbuild recipe; no files changed')
marker = '# AnimeJaNai AH-344 exact DML source-pair lifetime'
step = r'''
# AnimeJaNai AH-344 exact DML source-pair lifetime
# A separate step preserves all pre-existing mpv PATCH_COMMAND operations.
ExternalProject_Add_Step(mpv aji-exact-dml-pair
    DEPENDEES patch
    DEPENDERS configure
    COMMAND python3 ${CMAKE_CURRENT_LIST_DIR}/prepare-mpv.py <SOURCE_DIR>
    DEPENDS ${CMAKE_CURRENT_LIST_DIR}/prepare-mpv.py
            ${CMAKE_CURRENT_LIST_DIR}/vf_animejanai-exact-pair.patch
)
ExternalProject_Add_Step(mpv aji-exact-dml-pair-provenance
    DEPENDEES copy-binary
    DEPENDERS copy-package-dir
    COMMAND ${CMAKE_COMMAND} -E copy <SOURCE_DIR>/aji-dml-pair-provenance.json ${CMAKE_CURRENT_BINARY_DIR}/mpv-package/aji-dml-pair-provenance.json
    COMMAND ${CMAKE_COMMAND} -E copy <SOURCE_DIR>/aji-dml-pair-provenance.json ${CMAKE_CURRENT_BINARY_DIR}/mpv-dev/aji-dml-pair-provenance.json
)
'''
if marker in text and step not in text:
    raise SystemExit('A different AH-344 hook is already present; no files changed')
for name in ('prepare-mpv.py','vf_animejanai-exact-pair.patch'):
    shutil.copy2(Path(__file__).with_name(name),root/'packages'/name)
if marker not in text: recipe.write_text(text+step)
print('Installed exact-pair preparation and provenance for both Windows archives')
