#!/usr/bin/env python3
"""Add the Linux-only Vulkan bridge to the pinned mpv source idempotently."""
from pathlib import Path
import shutil
import sys
root=Path(sys.argv[1]);source=Path(__file__).parent
for name in ['vf_animejanai_vulkan.c','aji_vulkan.h']:
    shutil.copy2(source/name,root/'video/filter'/name)
edits={
    'filters/user_filters.h':('extern const struct mp_user_filter_entry vf_animejanai;',
        'extern const struct mp_user_filter_entry vf_animejanai;\nextern const struct mp_user_filter_entry vf_animejanai_vulkan;'),
    'filters/user_filters.c':('    &vf_format,\n','    &vf_format,\n#ifndef _WIN32\n    &vf_animejanai_vulkan,\n#endif\n'),
    'meson.build':("cuda_hwaccel = get_option('cuda-hwaccel')", "if host_machine.system() == 'linux'\n    sources += files('video/filter/vf_animejanai_vulkan.c')\nendif\n\ncuda_hwaccel = get_option('cuda-hwaccel')")
}
for name,(old,new) in edits.items():
    p=root/name;text=p.read_text()
    if new in text:continue
    assert text.count(old)==1,f'Unexpected mpv source layout: {name}'
    p.write_text(text.replace(old,new))
print('Linux Vulkan filter installed; CUDA/D3D11 code unchanged')
