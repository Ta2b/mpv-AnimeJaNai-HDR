#!/usr/bin/env python3
"""Add the Linux-only Vulkan bridge to the pinned mpv source idempotently."""
from pathlib import Path
import shutil
import re
import sys
root=Path(sys.argv[1]);source=Path(__file__).parent
for name in ['vf_animejanai_vulkan.c','aji_vulkan.h']:
    shutil.copy2(source/name,root/'video/filter'/name)
# Pure-C optional Surface ABI headers for the native CUDA worker client.
surface_headers=root/'video/filter/aji_surface'
surface_headers.mkdir(exist_ok=True)
for name in ['surface.h','surface_async.h','interpolator.h','pipeline.h']:
    shutil.copy2(source.parent/'common'/name,surface_headers/name)
edits={
    'filters/user_filters.h':('extern const struct mp_user_filter_entry vf_animejanai;',
        'extern const struct mp_user_filter_entry vf_animejanai;\nextern const struct mp_user_filter_entry vf_animejanai_vulkan;'),
    'filters/user_filters.c':('    &vf_format,\n','    &vf_format,\n#ifndef _WIN32\n    &vf_animejanai_vulkan,\n#endif\n'),
    'meson.build':("cuda_hwaccel = get_option('cuda-hwaccel')", "if host_machine.system() != 'windows'\n    sources += files('video/filter/vf_animejanai_vulkan.c')\nendif\n\ncuda_hwaccel = get_option('cuda-hwaccel')")
}
for name,(old,new) in edits.items():
    p=root/name;text=p.read_text()
    if new in text:continue
    assert text.count(old)==1,f'Unexpected mpv source layout: {name}'
    p.write_text(text.replace(old,new))
# mpv uses optional queue labels introduced in Wayland 1.23. They otherwise
# require a newer host client library even though the event queue behavior is
# identical. Keep the public unnamed API for Ubuntu 24.04's Wayland 1.22.
p = root / 'video/out/wayland_common.c'
text = p.read_text()
if 'wl_display_create_queue_with_name(' in text:
    text, count = re.subn(r'wl_display_create_queue_with_name\(([^,]+),\s*"[^"]*"\)',
                         r'wl_display_create_queue(\1)', text)
    assert count == 2 and 'wl_display_create_queue_with_name(' not in text, 'Unexpected Wayland queue calls'
    p.write_text(text)
print('Linux Vulkan filter and Wayland queue compatibility installed; CUDA/D3D11 code unchanged')
