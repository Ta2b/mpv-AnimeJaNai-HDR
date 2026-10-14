-- RIFE output rate matched to the display refresh. Pure functions: nothing here changes MPV.
local M = {}

local TOLERANCE = 0.002  -- 0.2 %: one repeated/dropped frame about every 20 s at 48 fps
local EXACT = 0.00001    -- a large fraction must be this close: one frame every ten minutes at 165

-- The fraction closest to x whose denominator is at most max_q (continued fractions).
local function fraction(x, max_q)
    local h0, h1, k0, k1 = 0, 1, 1, 0
    local y = x
    for _ = 1, 40 do
        local a = math.floor(y)
        local h2, k2 = a * h1 + h0, a * k1 + k0
        if k2 > max_q then break end
        h0, h1, k0, k1 = h1, h2, k1, k2
        local rest = y - a
        if rest < 1e-12 then break end
        y = 1 / rest
    end
    return h1, k1
end

-- Interpolation factor p/q (p/q <= max_factor) so that the output frame rate is the display
-- refresh divided by a whole number: every frame stays on screen for the same time. A small
-- fraction (q <= 4) is preferred; otherwise the exact ratio, e.g. 6875/999 for 23.976 fps on a
-- 165 Hz screen, which engines that make in-between frames from one RIFE run per pair can afford.
-- Returns p, q, output_fps, refreshes_per_frame; nil when no such factor exists.
function M.choose(source_fps, display_fps, max_factor)
    source_fps, display_fps = tonumber(source_fps), tonumber(display_fps)
    max_factor = tonumber(max_factor) or 2
    if not source_fps or not display_fps or source_fps <= 0 or display_fps <= 0 then return nil end
    for n = 1, 16 do
        local out = display_fps / n
        local f = out / source_fps
        if f < 1 - TOLERANCE then return nil end
        if f <= max_factor * (1 + TOLERANCE) then
            for q = 1, 4 do
                local p = math.floor(f * q + 0.5)
                if p >= q and math.abs(p / q - f) / f <= TOLERANCE then
                    return p, q, source_fps * p / q, n
                end
            end
            local p, q = fraction(f, 10000)
            if p >= q and math.abs(p / q - f) / f <= EXACT then
                return p, q, source_fps * p / q, n
            end
        end
    end
    return nil
end

-- The conf with every RIFE chain set to p/q. Lines are kept as they are otherwise.
-- Returns the new text and whether anything changed.
function M.rewrite(text, p, q)
    local lines, rife, section = {}, {}, nil
    for line in (text .. '\n'):gmatch('([^\n]*)\n') do lines[#lines + 1] = line end
    if lines[#lines] == '' then lines[#lines] = nil end
    -- First pass: chains with RIFE enabled, per section.
    for _, line in ipairs(lines) do
        local sec = line:match('^%s*%[([^%]]+)%]')
        if sec then section = sec end
        local chain, value = line:match('^%s*chain_(%d+)_rife%s*=%s*(%S+)')
        if section and chain then
            value = value:lower()
            if value == 'yes' or value == 'true' or value == '1' then
                rife[section .. ':' .. chain] = true
            end
        end
    end
    local out, changed, seen = {}, false, {}
    section = nil
    local function flush_missing(sec)
        -- Chains of the finished section that had no factor lines: add them.
        if not sec then return end
        for key in pairs(rife) do
            local s, chain = key:match('^(.*):(%d+)$')
            if s == sec then
                for _, kind in ipairs({'numerator', 'denominator'}) do
                    if not seen[key .. kind] then
                        out[#out + 1] = string.format('chain_%s_rife_factor_%s=%d', chain, kind,
                            kind == 'numerator' and p or q)
                        changed = true
                    end
                end
            end
        end
    end
    for _, line in ipairs(lines) do
        local sec = line:match('^%s*%[([^%]]+)%]')
        if sec then
            flush_missing(section)
            section = sec
            out[#out + 1] = line
        else
            local chain, kind = line:match('^%s*chain_(%d+)_rife_factor_(%a+)%s*=')
            local key = section and chain and (section .. ':' .. chain)
            if key and rife[key] and (kind == 'numerator' or kind == 'denominator') then
                seen[key .. kind] = true
                local new = string.format('chain_%s_rife_factor_%s=%d', chain, kind, kind == 'numerator' and p or q)
                if new ~= line then changed = true end
                out[#out + 1] = new
            else
                out[#out + 1] = line
            end
        end
    end
    flush_missing(section)
    return table.concat(out, '\n') .. '\n', changed
end

-- [global] display_rate_match=yes (AnimeJaNai 3.8 automatic refresh): the player picks the
-- refresh for the video, so the profile's own factor is kept.
function M.display_rate_match(text)
    local section
    for line in (text or ''):gmatch('[^\n]+') do
        local sec = line:match('^%s*%[([^%]]+)%]')
        if sec then section = sec end
        local v = section == 'global' and line:match('^%s*display_rate_match%s*=%s*(%S+)')
        if v then v = v:lower(); return v == 'yes' or v == 'true' end
    end
    return false
end

return M
