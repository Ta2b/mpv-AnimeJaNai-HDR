-- On-demand observed reference; no polling or change to playback settings.
local mp = require 'mp'
local utils = require 'mp.utils'
local busy, serial = false, 0
local function path(value) return mp.command_native({'expand-path', value}) end
local function export()
    if busy then mp.osd_message('Export de référence déjà en cours'); return end
    local root = os.getenv('ANIMEJANAI_ROOT') or path('~~/..')
    local bundle = os.getenv('ANIMEJANAI_BUNDLE') or root
    local windows = package.config:sub(1,1) == '\\'
    local helper = utils.join_path(bundle, windows and 'AnimeJaNaiPlatform.exe' or 'AnimeJaNaiPlatform')
    local ipc = os.getenv('ANIMEJANAI_IPC_PATH') or mp.get_property('options/input-ipc-server')
    if not ipc or ipc == '' then mp.osd_message('Export impossible : IPC mpv indisponible'); return end
    if not utils.file_info(helper) then mp.osd_message('Export impossible : AnimeJaNaiPlatform absent'); return end
    serial = serial + 1
    local output = utils.join_path(root, 'animejanai/diagnostics/reference-'
        .. os.date('!%Y%m%dT%H%M%SZ') .. '-' .. tostring(mp.get_property_native('pid')) .. '-' .. serial .. '.json')
    busy = true
    mp.osd_message('Export de référence en cours (lecture des empreintes)…')
    mp.command_native_async({name='subprocess', playback_only=false, capture_stdout=true, capture_stderr=true,
        args={helper, '--export-reference', '--root', bundle, '--mpv-ipc', ipc, '--output', output}},
        function(success, result, error)
            busy = false
            if success and result and result.status == 0 then
                mp.osd_message('Référence exportée : ' .. output, 8)
            else
                local detail = result and result.stderr or error or 'erreur inconnue'
                mp.msg.error('Export de référence : ' .. detail)
                mp.osd_message('Échec export de référence : ' .. detail, 8)
            end
        end)
end
mp.register_script_message('animejanai-export-reference', export)
mp.add_key_binding(nil, 'export-reference', export)
