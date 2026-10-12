-- HDR grade plan shared by NVIDIA (RTX TrueHDR) and AMD/Intel (MPV HDR).
-- Pure functions: nothing here changes MPV. The controller applies the plan.
local M = {}

M.shader = '~~/user-shaders/anime-hdr-grade.hook'
M.prefix = 'anime-hdr-grade/'
M.keys = {'peak','paper','in_max','shadows','shadow_knee','area_gain','spec_gain','vibrance','abl','gamut_p3',
    'emulate','sdr_white','em_base','em_lo','em_hi','em_sat'}
-- Render options owned by the controller; restored to their startup values otherwise.
M.render_keys = {'target-trc','target-peak','target-contrast','target-gamut','hdr-reference-white',
    'sub-hdr-peak','image-subs-hdr-peak','hdr-compute-peak'}

-- Ctrl+G "natural" step: a softer look on top of the same display description.
M.presets = {
    natural = {shadows = 0.15, highlights = 0.50, highlights_rtx = 0.25, vibrance = 0.15, vibrance_rtx = 0.10},
}

local function clamp(v, lo, hi) return math.max(lo, math.min(hi, v)) end

-- Shared keys take precedence; the suffix is only a compatibility fallback.
function M.display(o, vendor)
    local suffix = vendor == 'nvidia' and 'nvidia' or 'amd'
    local function value(shared, legacy, fallback)
        return o[shared] and o[shared] ~= '' and o[shared] or o[legacy] or fallback
    end
    return {peak = value('display_peak','peak_' .. suffix,'auto'),
        gamut = value('display_gamut','gamut_' .. suffix,'auto'),
        oled = value('display_oled','oled_' .. suffix,'no')}
end

local function number_or_nil(v)
    local n = tonumber(v)
    if n and n == n then return n end
    return nil
end

-- ctx fields:
--   vendor        'nvidia' | 'amd' | 'intel' | 'unknown'
--   backend       'rtx' | 'mpv' | 'none' (SDR -> HDR conversion disabled)
--   source        'sdr' | 'hdr' | 'unknown'
--   windows       Windows HDR state confirmed by the coordinator: 'on' | other
--   truehdr       TrueHDR filter present and its PQ output confirmed
--   target_gamma  video-target-params/gamma
--   target_peak   video-target-params/max-luma (nits)
--   enabled       runtime A/B switch (Ctrl+G)
--   original      startup values of M.render_keys
-- Returns {render = {option = value}, active = bool, params = {...}, mode = string}.
function M.plan(o, ctx, preset)
    if preset then
        local merged = {}
        for k, v in pairs(o) do merged[k] = v end
        for k, v in pairs(preset) do merged[k] = v end
        o = merged
    end
    local original = ctx.original or {}
    local render = {}
    for _, k in ipairs(M.render_keys) do render[k] = original[k] end
    local result = {render = render, active = false, params = nil, mode = 'off'}
    local output_hdr = ctx.output_hdr
    if output_hdr == nil then output_hdr = ctx.windows == 'on' end
    if not output_hdr or (ctx.source ~= 'sdr' and ctx.source ~= 'hdr') then return result end

    -- HDR output confirmed: apply the common display description.
    local display = M.display(o, ctx.vendor)
    local fixed_peak = number_or_nil(display.peak)
    if fixed_peak then render['target-peak'] = tostring(clamp(fixed_peak, 100, 10000)) end
    if display.oled == 'yes' then render['target-contrast'] = 'inf' end
    if display.gamut ~= 'auto' then render['target-gamut'] = display.gamut end
    if o.subtitle_white then
        render['sub-hdr-peak'] = tostring(o.subtitle_white)
        render['image-subs-hdr-peak'] = tostring(o.subtitle_white)
    end

    local peak = clamp(fixed_peak or number_or_nil(ctx.target_peak) or 1000, 100, 10000)
    -- Paper white stays below the peak so that highlights keep some headroom.
    local paper = math.floor(math.min(o.paper_white, 0.75 * peak) + 0.5)
    local mpv_sdr = ctx.backend == 'mpv' and ctx.source == 'sdr'
    if mpv_sdr then
        -- SDR white placed at paper white; the shader creates the highlights.
        render['target-trc'] = 'pq'
        -- TrueHDR look: the shader rebuilds the tone curve from SDR placed at 203 nits.
        render['hdr-reference-white'] = tostring(o.mpv_truehdr_look and 203 or paper)
    end
    if ctx.backend == 'rtx' and ctx.source == 'sdr' and ctx.truehdr then
        -- TrueHDR is tagged at the display peak and must pass through as it is. With peak
        -- detection MPV still measures every frame and applies a dynamic bt.2390 curve.
        render['hdr-compute-peak'] = 'no'
    end

    if ctx.backend == 'none' or not o.grade or not ctx.enabled or ctx.target_gamma ~= 'pq' then
        result.mode = 'neutral'
        return result
    end
    local graded
    if ctx.source == 'hdr' then graded = o.grade_native_hdr and 'native'
    elseif mpv_sdr then graded = 'mpv'
    elseif ctx.truehdr then graded = 'rtx' end
    if not graded then
        result.mode = 'neutral'
        return result
    end

    local p = {peak = peak, paper = paper, shadows = o.shadows, shadow_knee = 0.25 * paper,
        gamut_p3 = (render['target-gamut'] == 'display-p3') and 1 or 0,
        -- OLED: highlights are moderated on bright scenes, where the panel limits its power anyway.
        abl = display.oled == 'yes' and 0.6 or 0}
    -- TrueHDR look (measured on the RTX Video SDK): the shader first applies TrueHDR's tone
    -- curve, contrast and saturation to MPV's SDR, then the same grade as on real TrueHDR.
    local look = graded == 'mpv' and o.mpv_truehdr_look and true or false
    p.emulate, p.sdr_white, p.em_base, p.em_lo, p.em_hi, p.em_sat = 0, 203, 200, 1, 1, 1
    if look then
        local contrast = clamp(((o.mpv_contrast or 100) - 100) / 100, 0, 1)
        local saturation = clamp(((o.mpv_saturation or 100) - 100) / 100, 0, 1)
        p.emulate = 1
        p.em_base = clamp(4 * (o.mpv_middle_gray or 50), 40, math.min(400, 0.5 * peak))
        p.em_lo, p.em_hi, p.em_sat = 1 + 0.38 * contrast, 1 + 0.29 * contrast, 1 + 0.2 * saturation
    end
    if graded == 'mpv' and not look then
        -- SDR stops at paper white: isolated whites may reach the peak,
        -- large white areas only +50 % at highlights=1.
        local room = peak / paper
        p.in_max = paper
        p.area_gain = math.min(1 + 0.5 * o.highlights, room)
        p.spec_gain = math.max(p.area_gain, 1 + o.highlights * (room - 1))
        p.vibrance = o.vibrance
    else
        -- TrueHDR / native HDR already reach the peak: keep areas, lift isolated highlights.
        -- Their midtones (skin included) can sit well above 203 nits, depending on the
        -- RTX "middle grey": highlights only start from half the peak.
        p.paper = 0.5 * peak
        p.in_max = peak
        p.area_gain = 1
        p.spec_gain = 1 + 1.2 * o.highlights_rtx
        p.vibrance = o.vibrance_rtx
    end
    -- Stay inside the //!PARAM ranges of the shader (MPV rejects other values).
    p.area_gain = clamp(p.area_gain, 1, 4)
    p.spec_gain = clamp(p.spec_gain, p.area_gain, 20)
    result.active, result.params, result.mode = true, p, graded
    return result
end

-- glsl-shader-opts with only our keys replaced; other shaders' options are kept.
function M.shader_opts(current, params)
    local out = {}
    for k, v in pairs(current or {}) do
        if k:sub(1, #M.prefix) ~= M.prefix then out[k] = v end
    end
    if params then
        for _, k in ipairs(M.keys) do out[M.prefix .. k] = string.format('%.4f', params[k]) end
    end
    return out
end

-- glsl-shaders with our shader present once (active) or absent; others untouched.
function M.shader_list(current, active, expanded)
    local function ours(path)
        local norm = path:gsub('\\', '/'):lower()
        return norm == M.shader:lower() or (expanded and norm == expanded:gsub('\\', '/'):lower())
    end
    local out, found = {}, false
    for _, path in ipairs(current or {}) do
        if ours(path) then
            if active and not found then out[#out + 1] = path; found = true end
        else
            out[#out + 1] = path
        end
    end
    if active and not found then out[#out + 1] = M.shader end
    return out
end

local function same_map(a, b)
    for k, v in pairs(a) do if b[k] ~= v then return false end end
    for k, v in pairs(b) do if a[k] ~= v then return false end end
    return true
end
M.same_map = same_map

function M.same_list(a, b)
    if #a ~= #b then return false end
    for i = 1, #a do if a[i] ~= b[i] then return false end end
    return true
end

return M
