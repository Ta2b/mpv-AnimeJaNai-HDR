# Sources of the HDR helper binaries

The HDR overlay (`portable_config/hdr-tools/` and `portable_config/user-scripts/`) ships three
binaries. Their sources:

| Binary | What it does | Source |
|---|---|---|
| `hdr-tools/hdr-coordinator.exe` | Switches Windows HDR on/off per display with leases per player process, so several mpv windows do not fight over it and the previous state is restored. | `hdr-coordinator/` (C#, decompiled with ILSpy by the *HDR tools sources* workflow) |
| `user-scripts/display-info.dll` | mpv C plugin: `user-data/display-info/*`, `user-data/display-list/*` and the `toggle-hdr-display` message. | [dyphire/mpv-display-plugin](https://github.com/dyphire/mpv-display-plugin) (GPL-2.0), unmodified |

The decompiled folders are regenerated on every change of the `.exe` files (or by running the
workflow by hand). `SOURCE-SHA256.txt` in each folder is the hash of the binary they were produced
from. Decompiled code compiles back to the same behavior but loses comments and local names.
