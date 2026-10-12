-- AnimeJaNai on macOS (Apple Silicon): upscaling through Core ML, in the ONNX Runtime engine.
-- Everything is read from the application bundle; caches and the statistics go to
-- ~/Library/Caches/AnimeJaNai. A profile bank placed in
-- ~/Library/Application Support/AnimeJaNai/animejanai.conf replaces the built-in one.
local mp = require 'mp'
local utils = require 'mp.utils'
local options = require 'mp.options'

local o = {
    default_slot = 1,   -- profile applied when a file opens; 0 = off
    device = 'ALL',     -- Core ML compute units: ALL, GPU, ANE (Neural Engine) or CPU
}
options.read_options(o, 'animejanai_mac')

local function expand(p) return mp.command_native({'expand-path', p}) end
local bundle = expand('~~osxbundle/')
local home = os.getenv('HOME') or ''
local cache = home .. '/Library/Caches/AnimeJaNai'
local user_bank = home .. '/Library/Application Support/AnimeJaNai/animejanai.conf'
local stats = cache .. '/currentanimejanai.log'
local engine = bundle .. '/animejanai/inference/libaji_ort.dylib'
local slot, failed = 0, false

mp.command_native({name = 'subprocess', args = {'mkdir', '-p', cache}, playback_only = false})

local function bank()
    if utils.file_info(user_bank) then return user_bank end
    return bundle .. '/animejanai/animejanai.conf'
end

local function read(path)
    local f = io.open(path, 'r')
    if not f then return nil end
    local s = f:read('*a')
    f:close()
    return s
end

local function profile_name(n)
    local text = read(bank()) or ''
    local section = text:match('%[slot_' .. n .. '%](.-)\n%[') or text:match('%[slot_' .. n .. '%](.*)$') or ''
    return section:match('profile_name=([^\r\n]*)')
end

local function select(value, quiet)
    local wanted = tonumber(value)
    if not wanted or wanted < 0 or wanted ~= math.floor(wanted) then return end
    if wanted > 0 and failed then
        mp.osd_message('AnimeJaNai : moteur en échec pour cette session, voir le terminal.', 5)
        wanted = 0
    end
    if wanted > 0 and not utils.file_info(engine) then
        mp.osd_message('AnimeJaNai : moteur introuvable dans l\'application.', 5)
        wanted = 0
    end
    if wanted > 0 and not profile_name(wanted) then
        mp.osd_message('AnimeJaNai : profil ' .. wanted .. ' vide', 4)
        return
    end
    local list = mp.get_property_native('vf') or {}
    for i = #list, 1, -1 do if list[i].label == 'aji' then table.remove(list, i) end end
    if wanted > 0 then
        table.insert(list, 1, {name = 'animejanai-vulkan', label = 'aji', enabled = true, params = {
            lib = engine, conf = bank(), ['model-dir'] = bundle .. '/animejanai/onnx',
            device = o.device, stats = stats, slot = tostring(wanted)}})
    end
    mp.set_property_native('vf', list)
    slot = wanted
    mp.set_property_native('user-data/animejanai-active-slot', slot)
    if not quiet then
        mp.osd_message(slot == 0 and 'AnimeJaNai : désactivé'
            or 'AnimeJaNai ' .. slot .. ' : ' .. tostring(profile_name(slot)), 4)
    end
end

mp.add_hook('on_preloaded', -50, function()
    local current = mp.get_property_native('user-data/animejanai-active-slot')
    select(current or o.default_slot, true)
end)

-- The filter disables itself on error (unsupported source, engine failure): say so once and
-- keep normal playback.
mp.observe_property('vf', 'native', function(_, list)
    if slot == 0 then return end
    for _, f in ipairs(list or {}) do
        if f.label == 'aji' and f.enabled == false then
            failed = true
            select(0, true)
            mp.msg.error('AnimeJaNai filter failed; disabled for this session.')
            mp.osd_message('AnimeJaNai : échec du moteur (voir le terminal). Lecture normale.', 8)
        end
    end
end)

-- Ctrl+1 to Ctrl+4: profiles; Ctrl+0: off; Ctrl+j: status. Bound here so that they work
-- whatever input.conf the user has.
for n = 0, 4 do
    mp.add_key_binding('Ctrl+' .. n, 'animejanai-' .. n, function() select(n, false) end)
end
mp.register_script_message('animejanai-select', function(value) select(value, false) end)
local function status()
    local text = 'AnimeJaNai (Core ML, ' .. o.device .. ') | profil ' .. slot
        .. (slot > 0 and (' : ' .. tostring(profile_name(slot))) or ' : désactivé') .. '\n'
        .. (slot > 0 and (read(stats) or 'statistiques indisponibles') or '')
    mp.osd_message(text, 8)
    mp.msg.info(text)
end
mp.add_key_binding('Ctrl+j', 'animejanai-status', status)
mp.register_script_message('animejanai-status', status)
mp.msg.info('AnimeJaNai macOS: bundle ' .. bundle .. ', engine ' .. (utils.file_info(engine) and 'found' or 'MISSING'))
