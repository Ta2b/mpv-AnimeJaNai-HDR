-- AnimeJaNai on macOS (Apple Silicon): upscaling through Core ML, in the ONNX Runtime engine.
-- The engine and the models are read from the application bundle (ANIMEJANAI_BUNDLE, set by the
-- launcher); caches and the statistics go to ~/Library/Caches/AnimeJaNai. The profiles are in
-- ~/Library/Application Support/AnimeJaNai/animejanai/animejanai.conf (created by the launcher).
--
-- There is no Manager on macOS, so the player settles on a profile this Mac can run by itself:
-- it measures the time the engine spends on each image and, when a profile cannot keep up with
-- the video, moves to the next lighter one and remembers it (auto_profile).
local mp = require 'mp'
local utils = require 'mp.utils'
local options = require 'mp.options'

local o = {
    default_slot = 1,   -- profile applied when a file opens; 0 = off
    -- Core ML compute units: ALL, GPU, ANE (Neural Engine) or CPU. Two names joined by + cut the
    -- frame in two bands processed at the same time, one per device: GPU+ANE.
    device = 'ALL',
    -- Lighter profile when the current one is slower than the video; remembered for this Mac.
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
local slot, failed = 0, false
-- From heaviest to lightest; 0 = off. Profiles 5 and 6 only exist for this ladder.
local ladder = {1, 5, 6, 0}
local manual = false          -- the user chose a profile: no automatic change in this session
local samples, seen, settled = {}, -1, false

mp.command_native({name = 'subprocess', args = {'mkdir', '-p', cache}, playback_only = false})

local function read(path)
    local f = io.open(path, 'r')
    if not f then return nil end
    local s = f:read('*a')
    f:close()
    return s
end

local function section(path, n)
    local text = read(path)
    if not text then return nil end
    text = text .. '\n['
    return text:match('%[slot_' .. n .. '%](.-)\n%[')
end

-- The user's bank when it has the profile; the application's own bank otherwise, so that a
-- bank written by an earlier version still gets the profiles added since.
local function bank_for(n)
    if section(user_bank, n) then return user_bank end
    if section(bundle_bank, n) then return bundle_bank end
    return nil
end

local function profile_name(n)
    local path = bank_for(n)
    return path and (section(path, n) or ''):match('profile_name=([^\r\n]*)')
end

local function reset_measure()
    samples, seen, settled = {}, -1, false
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
            lib = engine, conf = bank_for(wanted), ['model-dir'] = bundle .. '/animejanai/onnx',
            device = o.device, stats = stats, slot = tostring(wanted)}})
    end
    os.remove(stats)   -- the measure below must not read the previous profile's figures
    mp.set_property_native('vf', list)
    slot = wanted
    reset_measure()
    mp.set_property_native('user-data/animejanai-active-slot', slot)
    if not quiet then
        mp.osd_message(slot == 0 and 'AnimeJaNai : désactivé'
            or 'AnimeJaNai ' .. slot .. ' : ' .. tostring(profile_name(slot)), 4)
    end
end

-- The profile this Mac settled on earlier, if it is lighter than the configured one.
local function start_slot()
    local wanted = tonumber(o.default_slot) or 1
    if not o.auto_profile or wanted == 0 then return wanted end
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

local function median(values)
    local sorted = {}
    for i, v in ipairs(values) do sorted[i] = v end
    table.sort(sorted)
    return sorted[math.floor((#sorted + 1) / 2)]
end

-- Twice a second while a profile plays: the engine's time for its last image. The first images
-- are left out (Core ML compiles the model on the first one), then sixteen measures decide.
mp.add_periodic_timer(0.5, function()
    if not o.auto_profile or manual or settled or slot == 0 then return end
    if mp.get_property_native('pause') or mp.get_property_native('seeking') then return end
    local text = read(stats)
    if not text then return end
    local frames = tonumber(text:match('\nFrames: (%d+)'))
    local ms = tonumber(text:match('\nInference ms: ([%d%.]+)'))
    if not frames or not ms or frames == seen then return end
    seen = frames
    if frames < 12 then return end
    samples[#samples + 1] = ms
    if #samples < 16 then return end
    local fps = tonumber(mp.get_property_native('container-fps')) or 23.976
    local speed = tonumber(mp.get_property_native('speed')) or 1
    if fps <= 0 or fps > 121 then fps = 23.976 end
    local budget = 1000 / (fps * math.max(speed, 0.1)) * o.auto_budget
    local measured = median(samples)
    if measured <= budget then
        settled = true
        mp.msg.info(string.format('AnimeJaNai: profile %d holds %.1f ms per image for %.1f ms allowed', slot, measured, budget))
        return
    end
    local lighter
    for i, n in ipairs(ladder) do
        if n == slot then
            for k = i + 1, #ladder do
                if ladder[k] == 0 or profile_name(ladder[k]) then lighter = ladder[k]; break end
            end
        end
    end
    if not lighter then settled = true; return end   -- a profile of the user's own: left alone
    local was = slot
    mp.msg.warn(string.format('AnimeJaNai: profile %d takes %.1f ms per image for %.1f ms allowed; moving to %d',
        was, measured, budget, lighter))
    select(lighter, true)
    -- "Off" is not remembered: the next launch tries the lightest profile again, in case this
    -- one was slowed down by something else running.
    if lighter > 0 then
        local f = io.open(remembered, 'w')
        if f then f:write('slot=' .. lighter .. '\n'); f:close() end
    end
    mp.osd_message(string.format('AnimeJaNai : le profil %d demande %.0f ms par image, la vidéo en laisse %.0f.\n%s',
        was, measured, budget, lighter == 0 and 'Mise à l\'échelle désactivée sur ce Mac.'
            or ('Profil plus léger ' .. lighter .. ' : ' .. tostring(profile_name(lighter)))
            .. '\nCtrl+r : oublier ce choix et mesurer à nouveau.'), 10)
end)

mp.register_event('file-loaded', reset_measure)

-- Ctrl+1 to Ctrl+6: profiles; Ctrl+0: off; Ctrl+j: status. Bound here so that they work
-- whatever input.conf the user has. A profile chosen by hand is kept for the session.
local function choose(n)
    manual = true
    select(n, false)
end
for n = 0, 6 do
    mp.add_key_binding('Ctrl+' .. n, 'animejanai-' .. n, function() choose(n) end)
end
mp.register_script_message('animejanai-select', function(value) choose(value) end)
-- Forget the profile remembered for this Mac and measure again from the configured one.
mp.register_script_message('animejanai-auto-reset', function()
    os.remove(remembered)
    manual = false
    select(tonumber(o.default_slot) or 1, false)
end)
mp.add_key_binding('Ctrl+r', 'animejanai-auto-reset', function() mp.commandv('script-message', 'animejanai-auto-reset') end)
local function status()
    local text = 'AnimeJaNai (Core ML, ' .. o.device .. ') | profil ' .. slot
        .. (slot > 0 and (' : ' .. tostring(profile_name(slot))) or ' : désactivé')
        .. (o.auto_profile and not manual and ' | choix automatique' or '') .. '\n'
        .. (slot > 0 and (read(stats) or 'statistiques indisponibles') or '')
    mp.osd_message(text, 8)
    mp.msg.info(text)
end
mp.add_key_binding('Ctrl+j', 'animejanai-status', status)
mp.register_script_message('animejanai-status', status)
mp.msg.info('AnimeJaNai macOS: bundle ' .. bundle .. ', engine ' .. (utils.file_info(engine) and 'found' or 'MISSING'))
