-- RTX Video (Super Resolution + TrueHDR) inside the AnimeJaNai engine, for Vulkan output.
-- The engine reads animejanai-rtx.conf at configure and echoes the settings it used in its
-- stats log. Pure functions: nothing here changes MPV.
local M = {}

M.file = '~~/../animejanai/animejanai-rtx.conf'
M.tag = '@hdrtag:format:gamma=pq:primaries=bt.2020'

local function clamp(v, lo, hi, default)
    v = math.floor((tonumber(v) or default) + 0.5)
    return math.max(lo, math.min(hi, v))
end

-- s: hdr, vsr (booleans), w, h (target size or nil), quality, contrast, saturation,
-- middle_gray, peak. Same value ranges as the engine, so that the echo compares equal.
function M.settings(s)
    local w, h = tonumber(s.w), tonumber(s.h)
    if not w or not h or w < 2 or h < 2 then w, h = 0, 0 end
    return {
        {'hdr', s.hdr and 'yes' or 'no'},
        {'vsr', (s.vsr and w > 0) and 'yes' or 'no'},
        {'target', string.format('%dx%d', w, h)},
        {'vsr_quality', clamp(s.quality, 1, 4, 2)},
        {'contrast', clamp(s.contrast, 0, 200, 100)},
        {'saturation', clamp(s.saturation, 0, 200, 100)},
        {'middle_gray', clamp(s.middle_gray, 10, 100, 50)},
        {'peak', clamp(s.peak, 400, 2000, 1000)},
    }
end

local function join(settings, separator)
    local parts = {}
    for _, kv in ipairs(settings) do parts[#parts + 1] = kv[1] .. '=' .. tostring(kv[2]) end
    return table.concat(parts, separator)
end

-- Content of animejanai-rtx.conf.
function M.text(s)
    return '# Written by animejanai_hdr_auto.lua (render_api=vulkan); read by the engine at configure.\n'
        .. join(M.settings(s), '\n') .. '\n'
end

-- The line the engine writes in its stats log for these settings.
function M.echo(s)
    return 'RTX Video Settings: ' .. join(M.settings(s), ' ')
end

-- What the engine reports for the current file: settings echo (nil when the chain is not
-- active or the stage is not installed) and the stages really applied.
function M.applied(stats)
    stats = stats or ''
    local line = stats:match('Applied RTX Video:[^\r\n]*')
    return {
        echo = stats:match('RTX Video Settings:[^\r\n]*'),
        hdr = line ~= nil and line:find('TrueHDR', 1, true) ~= nil,
        vsr = line ~= nil and line:find('Super Resolution', 1, true) ~= nil,
        line = line,
        missing = stats:find('aji_rtx is not installed', 1, true) ~= nil
            or stats:find('RTX Video is not available', 1, true) ~= nil,
    }
end

return M
