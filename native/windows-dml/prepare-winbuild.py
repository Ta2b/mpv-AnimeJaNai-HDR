#!/usr/bin/env python3
"""Prepare the pinned existing static winbuild recipe; never use floating refs."""
from pathlib import Path
import re
import shutil
import subprocess
import sys

WINBUILD = '597bab33931cbd2ec29abe9d44a29e6363da7499'
RECIPE = '1f8d2e76255abc48f0456d9be99b4cab9c6566e6'
MPV = '19c0fcf89595e6ab33908299207c555b67e81558'
LIBASS = '896614fa263f9f64944f7b8650ff6806d5328c4d'
LIBPLACEBO = '0d043c7f6f79cd3687c023454bdacbe615e4d96f'
root, driver = (Path(x).resolve() for x in sys.argv[1:3])
for directory, expected in ((root, RECIPE), (driver, WINBUILD)):
    actual = subprocess.check_output(['git','-C',str(directory),'rev-parse','HEAD'],text=True).strip()
    if actual != expected: raise SystemExit(f'Unexpected build source {directory}: {actual}')
# Keep the established Windows fixes from the driver. Any conflict stops CI.
for patch in sorted((driver/'patch').glob('*.patch')):
    # This pinned recipe no longer applies its historical Vulkan loader patch.
    # The driver's rebase of that unused patch is obsolete, not a build fix.
    if patch.name == '0013-vulkan-rebase-patch.patch' and 'PATCH_COMMAND' not in (root/'packages/vulkan.cmake').read_text():
        print('Omit obsolete rebase of an unused Vulkan loader patch')
        continue
    reverse = subprocess.run(['git','-C',str(root),'apply','--reverse','--check',str(patch)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if reverse.returncode == 0:
        print(f'Already included by the pinned recipe: {patch.name}')
        continue
    subprocess.run(['git','-C',str(root),'apply','--check',str(patch)],check=True)
    subprocess.run(['git','-C',str(root),'apply',str(patch)],check=True)

def edit(name, old, new):
    p=root/name;s=p.read_text()
    if s.count(old) != 1: raise SystemExit(f'Expected one anchor in {name}: {old}')
    p.write_text(s.replace(old,new))
# The recipe's reset helper assumes @{u} even after GIT_TAG selected a
# detached commit. Keep pinned sources pinned during post-install cleanup;
# preserve the original tracking-branch behavior for the other dependencies.
edit('cmake/custom_steps.cmake', '''    if("${git_remote_name}" STREQUAL "" AND NOT "${git_tag}" STREQUAL "")
        # GIT_REMOTE_NAME is not set when commit hash is specified
        set(reset "")''', '''    set(compare_ref "@{u}")
    string(LENGTH "${git_tag}" tag_length)
    if(tag_length EQUAL 40 AND "${git_tag}" MATCHES "^[0-9a-fA-F]+$")
        set(reset "${git_tag}")
        set(compare_ref "${git_tag}")
    elseif("${git_remote_name}" STREQUAL "" AND NOT "${git_tag}" STREQUAL "")
        # GIT_REMOTE_NAME is not set when commit hash is specified
        set(reset "")''')
edit('cmake/custom_steps.cmake', '$(git -C ${source_dir} rev-parse @{u})',
     '$(git -C ${source_dir} rev-parse ${compare_ref})')
edit('packages/mpv.cmake','GIT_REPOSITORY https://github.com/mpv-player/mpv.git',
     f'GIT_REPOSITORY https://github.com/the-database/mpv.git\n    GIT_TAG {MPV}')
edit('packages/libass.cmake','GIT_REPOSITORY https://github.com/libass/libass.git',
     f'GIT_REPOSITORY https://github.com/the-database/libass.git\n    GIT_TAG {LIBASS}')
edit('packages/libass.cmake','-Dlibunibreak=enabled','-Dlibunibreak=enabled\n        -Dthreads=enabled')
edit('packages/libplacebo.cmake','GIT_REPOSITORY https://github.com/haasn/libplacebo.git',
     f'GIT_REPOSITORY https://github.com/haasn/libplacebo.git\n    GIT_TAG {LIBPLACEBO}')
for name in ('libplacebo-present-queue.patch','libplacebo-nvidia-rtx-hdr.patch'):
    shutil.copy2(driver/name,root/'packages'/name)
edit('packages/libplacebo.cmake','    UPDATE_COMMAND ""',
     '    UPDATE_COMMAND ""\n    PATCH_COMMAND ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> git apply --ignore-space-change ${CMAKE_CURRENT_LIST_DIR}/libplacebo-present-queue.patch ${CMAKE_CURRENT_LIST_DIR}/libplacebo-nvidia-rtx-hdr.patch')
# Preserve the driver fixes for unreliable GNU downloads and libaribcaption.
for p in (root/'packages').glob('*.cmake'):
    s=p.read_text()
    s=re.sub(r'(?m)^( *URL )https://ftp\.gnu\.org/(?:pub/)?gnu/([^ \n]+)$',
             r'\1https://ftp.gnu.org/gnu/\2 https://mirrors.kernel.org/gnu/\2 https://ftpmirror.gnu.org/\2',s)
    if p.name=='libaribcaption.cmake': s='\n'.join(x for x in s.split('\n') if '-DHAVE_OPENSSL=1' not in x)
    p.write_text(s)
for filename, unwanted in (('CMakeLists.txt','ccache_conf.in'),('exec.in','ccache')):
    p=root/filename;p.write_text(''.join(x for x in p.read_text().splitlines(True) if unwanted not in x))
subprocess.run([sys.executable,str(Path(__file__).with_name('install-winbuild-hook.py')),str(root)],check=True)
# A restored source/prefix cache must not bypass the reviewed versions/hook.
for package in ('mpv','libass','libplacebo'):
    shutil.rmtree(root/'src_packages'/package,ignore_errors=True)
    for path in (root/'build64').glob(f'**/{package}-prefix'):
        shutil.rmtree(path)
print('Pinned recipe, existing Windows fixes and mandatory exact-pair hook prepared')
