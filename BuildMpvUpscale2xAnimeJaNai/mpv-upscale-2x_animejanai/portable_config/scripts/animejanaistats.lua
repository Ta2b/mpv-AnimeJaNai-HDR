local showing = false
local MAX_DURATION = 2147483

local function read_file(path)
    local file = io.open(path, "r")
    if not file then return nil end
    local content = file:read("*a")
    file:close()
    return content ~= "" and content or nil
end

local function refresh()
    if not showing then return end
    local message
    if (mp.get_property("vf") or "") == "" then
        message = "Upscaling is disabled"
    else
        local path = mp.command_native({'expand-path', "~~/../animejanai/currentanimejanai.log"})
        message = read_file(path) or "Waiting for AnimeJaNai statistics; press ~ for engine errors"
    end
    mp.osd_message(message, MAX_DURATION)
end

-- Producers publish complete snapshots up to four times a second. Refresh only
-- while visible; missing/empty snapshots do not masquerade as an engine failure.
local timer = mp.add_periodic_timer(0.25, refresh)
timer:kill()
mp.add_key_binding("Ctrl+j", "show_animejanai_stats", function()
    showing = not showing
    if showing then timer:resume(); refresh()
    else timer:kill(); mp.osd_message("") end
end)
