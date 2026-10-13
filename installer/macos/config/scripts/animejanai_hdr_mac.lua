-- SDR -> HDR conversion and grading on macOS: the same script as on Linux (the compositor owns
-- the display; mpv asks for a PQ / BT.2020 output and the shader builds the TrueHDR look).
-- Active when linux_hdr_output=pq in script-opts/animejanai_hdr_auto.conf.
local mp = require 'mp'
dofile(mp.command_native({'expand-path', '~~/hdr-tools/linux-hdr.lua'}))
mp.add_key_binding('Ctrl+g', 'animejanai-grade', function() mp.commandv('script-message', 'animejanai-grade-toggle') end)
mp.add_key_binding('Ctrl+i', 'animejanai-hdr-info', function() mp.commandv('script-message', 'animejanai-hdr-status') end)
mp.add_key_binding('Ctrl+Alt+p', 'animejanai-hdr-pattern', function() mp.commandv('script-message', 'animejanai-calibration') end)

-- Ctrl+h: SDR -> HDR conversion on / off. There is no Manager on macOS: the setting is written
-- to script-opts/animejanai_hdr_auto.conf (pq = convert, auto = the video's own format) and
-- applied at once.
local conf = mp.command_native({'expand-path', '~~/script-opts/animejanai_hdr_auto.conf'})
local function toggle_hdr()
    local f = io.open(conf, 'r')
    if not f then mp.osd_message('Réglages HDR introuvables : ' .. conf, 5); return end
    local text = '\n' .. f:read('*a')
    f:close()
    local current = text:match('\nlinux_hdr_output=(%w+)')
    local wanted = current == 'pq' and 'auto' or 'pq'
    if current then text = text:gsub('\nlinux_hdr_output=%w+', '\nlinux_hdr_output=' .. wanted, 1)
    else text = text .. (text:sub(-1) == '\n' and '' or '\n') .. 'linux_hdr_output=' .. wanted .. '\n' end
    f = io.open(conf, 'w')
    if not f then mp.osd_message('Réglages HDR non modifiables : ' .. conf, 5); return end
    f:write(text:sub(2))
    f:close()
    mp.commandv('script-message', 'animejanai-reload-options')
    mp.osd_message(wanted == 'pq' and 'Conversion SDR vers HDR : activée' or 'Conversion SDR vers HDR : désactivée (format de la vidéo)', 4)
end
mp.add_key_binding('Ctrl+h', 'animejanai-hdr-toggle', toggle_hdr)
mp.register_script_message('animejanai-hdr-toggle', toggle_hdr)
