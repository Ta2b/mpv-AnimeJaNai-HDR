-- AnimeJaNai on macOS (Apple Silicon). One engine library runs the models in three ways, chosen
-- by [global] backend in the profile bank: Core ML through ONNX Runtime (CoreML), Core ML alone
-- (CoreMLNative) or Metal (Metal). The Manager (Ctrl+E) writes these settings; this script
-- applies them:
--   backend             the engine (read by the engine itself)
--   apple_device        AUTO, GPU, NPU, CPU or GPU+NPU: where the model runs
--   engine_reuse        off, frame, tiles (read by the engine)
--   engine_boost        yes: Balanced on drawings that stay on screen (read by the engine)
--   engine_rife_device  auto, gpu, npu, cpu: the processor of RIFE (read by the engine)
--   apple_auto_profile  yes: move to a lighter profile when this Mac cannot keep up
--   default_slot        the profile applied when a file opens
-- The engine and the models are read from the application bundle (ANIMEJANAI_BUNDLE, set by the
-- launcher); caches and the statistics go to ~/Library/Caches/AnimeJaNai. The bank is
-- ~/Library/Application Support/AnimeJaNai/animejanai/animejanai.conf (created by the launcher).
local mp = require 'mp'
local utils = require 'mp.utils'
local options = require 'mp.options'

-- script-opts/animejanai_mac.conf: what applies when the bank does not say (banks written before
-- the Manager existed on macOS).
local o = {
    default_slot = 1,   -- profile applied when a file opens; 0 = off
    device = 'ALL',     -- ALL / AUTO, GPU, ANE / NPU, CPU, or two joined by +
    auto_profile = true,
    -- Part of the time between two images the engine may use (the rest is decoding and display).
    auto_budget = 0.85,
}
options.read_options(o, 'animejanai_mac')

local bundle = os.getenv('ANIMEJANAI_BUNDLE') or ''
local home = os.getenv('HOME') or ''
local cache = os.getenv('ANIMEJANAI_CACHE') or (home .. '/Library/Caches/AnimeJaNai')
local data = os.getenv('ANIMEJANAI_DATA_DIR') or (home .. '/Library/Application Support/AnimeJaNai/animejanai')
local user_bank = data .. '/animejanai.conf'
local bundle_bank = bundle .. '/animejanai/animejanai.conf'
local remembered = data .. '/auto-profile.txt'
local stats = cache .. '/currentanimejanai.log'
local engine = bundle .. '/animejanai/inference/libaji_ort.dylib'
local manager_app = bundle .. '/AnimeJaNai Manager.app'
local manager = manager_app .. '/Contents/MacOS/AnimeJaNaiManager-HDR'
local slot, failed = 0, false
-- From heaviest to lightest: Balanced then Performance at the source size, the same at 720p,
-- then 540p and 360p; 0 = off. A profile that is not in this list is never changed.
local ladder = {4, 2, 3, 1, 5, 6, 0}
local manual = false          -- the user chose a profile: no automatic change in this session
local seen = -1

mp.command_native({name = 'subprocess', args = {'mkdir', '-p', cache}, playback_only = false})

local function read(path)
    local f = io.open(path, 'r')
    if not f then return nil end
    local s = f:read('*a')
    f:close()
    return s
end

local function section(path, name)
    local text = read(path)
    if not text then return nil end
    text = '\n' .. text:gsub('\r', '') .. '\n['
    return text:match('\n%[' .. name .. '%]([^\n]*\n.-)\n%[')
end

-- A [global] setting of the user's bank, or nil.
local function global(key)
    local text = section(user_bank, 'global')
    if not text then return nil end
    local value = ('\n' .. text):match('\n' .. key .. '%s*=%s*([^\n]*)')
    return value and value:gsub('%s+$', '') or nil
end

-- The user's bank when it has the profile; the application's own bank otherwise, so that a
-- bank written by an earlier version still gets the profiles added since.
local function bank_for(n)
    if section(user_bank, 'slot_' .. n) then return user_bank end
    if section(bundle_bank, 'slot_' .. n) then return bundle_bank end
    return nil
end

local function profile_name(n)
    local path = bank_for(n)
    return path and ('\n' .. (section(path, 'slot_' .. n) or '')):match('\nprofile_name=([^\n]*)')
end

local function yes(value, fallback)
    if value == nil or value == '' then return fallback end
    value = value:lower()
    return value == 'yes' or value == 'true' or value == '1' or value == 'on'
end

local function setting_device() return global('apple_device') or o.device end
local function setting_auto() return yes(global('apple_auto_profile'), o.auto_profile) end
local function setting_engine() return global('backend') or 'CoreML' end
-- Models: the folder the launcher fills with links to the application's models (the Manager
-- lists it, and it may hold models of the user), or the application's own.
local function models_dir()
    if utils.file_info(data .. '/onnx') then return data .. '/onnx' end
    return bundle .. '/animejanai/onnx'
end

-- The same for the interpolation models (RIFE).
local function rife_dir()
    if utils.file_info(data .. '/rife') then return data .. '/rife' end
    return bundle .. '/animejanai/rife'
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
            lib = engine, conf = bank_for(wanted), ['model-dir'] = models_dir(), ['rife-model-dir'] = rife_dir(),
            device = setting_device(), stats = stats, slot = tostring(wanted)}})
    end
    os.remove(stats)   -- the measure below must not read the previous profile's figures
    mp.set_property_native('vf', list)
    slot = wanted
    seen = -1
    mp.set_property_native('user-data/animejanai-active-slot', slot)
    if not quiet then
        mp.osd_message(slot == 0 and 'AnimeJaNai : désactivé'
            or 'AnimeJaNai ' .. slot .. ' : ' .. tostring(profile_name(slot)), 4)
    end
end

local function configured_slot()
    return tonumber(global('default_slot')) or tonumber(o.default_slot) or 1
end

-- The profile this Mac settled on earlier, if it is lighter than the configured one.
local function start_slot()
    local wanted = configured_slot()
    if not setting_auto() or wanted == 0 then return wanted end
    local saved = tonumber((read(remembered) or ''):match('slot=(%d+)'))
    if not saved then return wanted end
    local rank = {}
    for i, n in ipairs(ladder) do rank[n] = i end
    if rank[saved] and rank[wanted] and rank[saved] > rank[wanted] then return saved end
    return wanted
end

mp.add_hook('on_preloaded', -50, function()
    local current = mp.get_property_native('user-data/animejanai-active-slot')
    select(current or start_slot(), true)
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

-- Twice a second while a profile plays: the engine's own average over its last 48 images
-- ("Recent ms"). Frames it reuses cost almost nothing, so the average follows what the video
-- really asks: a profile is too heavy when that average stays above the time between two images.
mp.add_periodic_timer(0.5, function()
    if not setting_auto() or manual or slot == 0 then return end
    if mp.get_property_native('pause') or mp.get_property_native('seeking') then return end
    local text = read(stats)
    if not text then return end
    local frames = tonumber(text:match('\nFrames: (%d+)'))
    local recent = tonumber(text:match('\nRecent ms: ([%d%.]+)'))
    if not frames or not recent or frames == seen then return end
    seen = frames
    -- The first images are left out: the model is compiled on the first one, and the average
    -- must be over a full window.
    if frames < 72 then return end
    local fps = tonumber(mp.get_property_native('container-fps')) or 23.976
    local speed = tonumber(mp.get_property_native('speed')) or 1
    if fps <= 0 or fps > 121 then fps = 23.976 end
    local budget = 1000 / (fps * math.max(speed, 0.1)) * o.auto_budget
    if recent <= budget then return end
    local lighter
    for i, n in ipairs(ladder) do
        if n == slot then
            for k = i + 1, #ladder do
                if ladder[k] == 0 or profile_name(ladder[k]) then lighter = ladder[k]; break end
            end
        end
    end
    if not lighter then return end   -- a profile of the user's own: left alone
    local was = slot
    mp.msg.warn(string.format('AnimeJaNai: profile %d takes %.1f ms per image for %.1f ms allowed; moving to %d',
        was, recent, budget, lighter))
    select(lighter, true)
    -- "Off" is not remembered: the next launch tries the lightest profile again, in case this
    -- one was slowed down by something else running.
    if lighter > 0 then
        local f = io.open(remembered, 'w')
        if f then f:write('slot=' .. lighter .. '\n'); f:close() end
    end
    mp.osd_message(string.format('AnimeJaNai : le profil %d demande %.0f ms par image, la vidéo en laisse %.0f.\n%s',
        was, recent, budget, lighter == 0 and 'Mise à l\'échelle désactivée sur ce Mac.'
            or ('Profil plus léger ' .. lighter .. ' : ' .. tostring(profile_name(lighter)))
            .. '\nCtrl+r : oublier ce choix et mesurer à nouveau.'), 10)
end)

-- Ctrl+1 to Ctrl+9: profiles; Ctrl+0: off; Ctrl+j: status; Ctrl+e: Manager; Ctrl+r: measure
-- again (Ctrl+u, update, is bound by animejanai_update.lua). Bound here so that they work
-- whatever input.conf the user has. A profile chosen by hand is kept for the session.
local function choose(n)
    manual = true
    select(n, false)
end
for n = 0, 9 do
    mp.add_key_binding('Ctrl+' .. n, 'animejanai-' .. n, function() choose(n) end)
end
mp.register_script_message('animejanai-select', function(value) choose(value) end)
-- Forget the profile remembered for this Mac and measure again from the configured one.
mp.register_script_message('animejanai-auto-reset', function()
    os.remove(remembered)
    manual = false
    select(configured_slot(), false)
end)
mp.add_key_binding('Ctrl+r', 'animejanai-auto-reset', function() mp.commandv('script-message', 'animejanai-auto-reset') end)

-- The Manager saved settings: the engine reads its own when the filter is created again.
mp.register_script_message('animejanai-reload-options', function()
    failed = false
    if slot > 0 and not profile_name(slot) then select(configured_slot(), true) else select(slot, true) end
    mp.osd_message('AnimeJaNai : réglages appliqués (' .. setting_engine() .. ', ' .. setting_device() .. ')', 3)
end)

-- Ctrl+e: the Manager, with this player's folders and its socket in the environment. Opened
-- through the system: its window comes to the front, and a Manager that is already open is shown
-- again instead of a second one.
local function open_manager()
    if not utils.file_info(manager) then
        mp.osd_message('AnimeJaNai Manager introuvable dans l\'application.', 5)
        return
    end
    local args = {'/usr/bin/open', '-a', manager_app}
    for _, name in ipairs({'ANIMEJANAI_IPC_PATH', 'ANIMEJANAI_DATA_DIR', 'ANIMEJANAI_ROOT', 'ANIMEJANAI_BUNDLE'}) do
        local value = os.getenv(name)
        if value and value ~= '' then
            args[#args + 1] = '--env'
            args[#args + 1] = name .. '=' .. value
        end
    end
    mp.command_native_async({name = 'subprocess', args = args, playback_only = false, capture_stderr = true}, function(ok, result)
        if ok and result and result.status == 0 then return end
        -- A system whose "open" does not pass variables: the program itself, started by this
        -- player and with its environment.
        mp.command_native_async({name = 'subprocess', args = {manager}, playback_only = false, detach = true}, function() end)
    end)
    mp.osd_message('AnimeJaNai Manager', 2)
end
mp.add_key_binding('Ctrl+e', 'animejanai-manager', open_manager)
mp.register_script_message('animejanai-manager', open_manager)

local function status()
    local version = (read(bundle .. '/version.txt') or ''):gsub('%s+$', '')
    -- No statistics yet: the engine has not given a picture since the profile was chosen. It
    -- compiles its models when a profile opens, and the picture stays still meanwhile.
    local waiting = 'Le moteur prépare les modèles de ce profil : l\'image reste figée pendant ce temps.\n'
        .. 'La première fois, cela peut durer de quelques dizaines de secondes à quelques minutes\n'
        .. '(plus long avec RIFE) ; le résultat est gardé pour les fois suivantes.'
    local text = 'AnimeJaNai ' .. version .. ' | moteur ' .. setting_engine() .. ' | cible ' .. setting_device() .. ' | profil ' .. slot
        .. (slot > 0 and (' : ' .. tostring(profile_name(slot))) or ' : désactivé')
        .. (setting_auto() and not manual and ' | choix automatique' or '') .. '\n'
        .. (slot > 0 and (read(stats) or waiting) or '')
    mp.osd_message(text, 10)
    mp.msg.info(text)
end
mp.add_key_binding('Ctrl+j', 'animejanai-status', status)
mp.register_script_message('animejanai-status', status)
mp.msg.info('AnimeJaNai macOS: bundle ' .. bundle .. ', engine ' .. (utils.file_info(engine) and 'found' or 'MISSING')
    .. ', ' .. setting_engine() .. ' on ' .. setting_device())
