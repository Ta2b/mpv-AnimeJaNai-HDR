-- SDR -> HDR conversion and grading on macOS: the same script as on Linux (the compositor owns
-- the display; mpv asks for a PQ / BT.2020 output and the shader builds the TrueHDR look).
-- Active when linux_hdr_output=pq in script-opts/animejanai_hdr_auto.conf.
local mp = require 'mp'
dofile(mp.command_native({'expand-path', '~~/hdr-tools/linux-hdr.lua'}))
mp.add_key_binding('Ctrl+g', 'animejanai-grade', function() mp.commandv('script-message', 'animejanai-grade-toggle') end)
mp.add_key_binding('Ctrl+i', 'animejanai-hdr-info', function() mp.commandv('script-message', 'animejanai-hdr-status') end)
