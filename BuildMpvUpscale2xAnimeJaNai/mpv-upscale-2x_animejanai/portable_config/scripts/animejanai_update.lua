-- On startup, asks AnimeJaNaiUpdater.exe whether a newer mpv-upscale-2x_animejanai release exists.
-- If so, shows a one-time OSD prompt; Ctrl+U (or the AnimeJaNai > Install Update menu entry, both
-- mapped to the "animejanai-update" script-message) applies it: the updater is launched detached,
-- mpv quits so files unlock, the update is applied in place (user files preserved), and mpv relaunches.
-- macOS: the install is an application, replaced as a whole; see start_update_mac below.
-- Ctrl+U asks again when no update is known: a release may have come out since the player was
-- opened, and a check that failed (no connection, GitHub refusing for a while) says so.

local mp = require 'mp'
local msg = require 'mp.msg'
local utils = require 'mp.utils'

local platform = mp.get_property("platform")
local is_mac = platform == "darwin"
-- The updater ships at the install root, one level above portable_config (~~/ = config dir);
-- on macOS inside the application, whose launcher gives its Resources folder.
local exe_name = platform == "windows" and "AnimeJaNaiUpdater.exe" or "AnimeJaNaiUpdater"
local updater = is_mac and ((os.getenv("ANIMEJANAI_BUNDLE") or "") .. "/" .. exe_name)
    or mp.command_native({ "expand-path", "~~/../" .. exe_name })
local available_version = nil

-- Inside an AppImage the install tree is a read-only squashfs, so the in-place
-- updater can't apply. AppRun sets ANIMEJANAI_APPIMAGE (APPIMAGE is set by the
-- runtime too); in that case we point the user at the new AppImage instead.
local is_appimage = os.getenv("ANIMEJANAI_APPIMAGE") ~= nil or os.getenv("APPIMAGE") ~= nil
local releases_url = "github.com/Ta2b/mpv-AnimeJaNai-HDR/releases"

-- macOS: why the application cannot be replaced where it is (the updater's UPDATE_BLOCKED).
local blocked = nil
local blocked_text = {
    translocated = "macOS is running a temporary copy of the application.\n" ..
        "Move it to the Applications folder with the Finder,\nopen it from there, then press Ctrl+U.",
    readonly = "The folder that holds the application cannot be written to.\n" ..
        "Move the application to the Applications folder, then press Ctrl+U.",
}
local updating = false

-- macOS: the updater downloads and verifies the new application while the video keeps playing,
-- and reports through a one-line file. When the application is ready the player closes (the
-- position in the video is kept), the application is replaced and the player comes back on the
-- same file.
local function start_update_mac()
    if updating then
        return
    end
    if blocked then
        mp.osd_message("AnimeJaNai " .. available_version .. " is available.\n" ..
            (blocked_text[blocked] or blocked), 14)
        return
    end
    updating = true
    local version = available_version
    local pid = tostring(mp.get_property_native("pid"))
    local status_file = (os.getenv("TMPDIR") or "/tmp"):gsub("/+$", "") .. "/animejanai-update-" .. pid .. ".status"
    os.remove(status_file)
    os.remove(status_file .. ".reopen")
    mp.command_native({
        name = "subprocess",
        args = { updater, "--apply", "--wait-pid", pid, "--status", status_file },
        detach = true,
        playback_only = false,
    })
    mp.osd_message("AnimeJaNai " .. version .. ": downloading. The video keeps playing.", 4)

    local started, shown, timer = mp.get_time(), nil, nil
    local function stop(text, seconds)
        timer:kill()
        updating = false
        os.remove(status_file)
        mp.osd_message(text, seconds)
    end
    timer = mp.add_periodic_timer(0.5, function()
        local f = io.open(status_file, "r")
        local line = f and f:read("*l") or nil
        if f then
            f:close()
        end
        if not line then
            if mp.get_time() - started > 30 then
                stop("AnimeJaNai update: the updater did not start.", 8)
            end
            return
        end
        if line == shown then
            return
        end
        shown = line
        local state, rest = line:match("^(%S+)%s*(.*)$")
        if state == "DOWNLOAD" then
            mp.osd_message("AnimeJaNai " .. version .. ": downloading " .. rest .. " %", 3)
        elseif state == "EXTRACT" then
            mp.osd_message("AnimeJaNai " .. version .. ": verifying...", 5)
        elseif state == "READY" then
            timer:kill()
            -- The file to come back to, as it is now (it may have changed during the download).
            local path = mp.get_property("path")
            if path then
                if not path:find("://") and path:sub(1, 1) ~= "/" then
                    path = utils.join_path(mp.get_property("working-directory") or "", path)
                end
                local reopen = io.open(status_file .. ".reopen", "w")
                if reopen then
                    reopen:write(path, "\n")
                    reopen:close()
                end
            end
            mp.osd_message("Installing AnimeJaNai " .. rest .. " - the player closes and comes back...", 5)
            mp.add_timeout(1.5, function() mp.command(path and "quit-watch-later" or "quit") end)
        elseif state == "UP_TO_DATE" then
            available_version = nil
            stop("AnimeJaNai is up to date.", 3)
        elseif state == "FAILED" then
            msg.error("Update failed: " .. rest)
            stop("AnimeJaNai update failed: " .. rest, 14)
        end
    end)
end

-- Asks the updater. done(state, detail): "update" (available_version is set), "none", or
-- "failed" with the updater's message when it gave one.
local function check(done)
    mp.command_native_async({
        name = "subprocess",
        args = { updater, "--check" },
        capture_stdout = true,
        playback_only = false,
    }, function(success, result)
        local out = result and result.stdout or ""
        if not success or not result or result.status ~= 0 then
            done("failed", out:match("Updater error:%s*([^\r\n]*)"))
            return
        end
        local ver = out:match("UPDATE_AVAILABLE%s+(%S+)")
        available_version = ver
        blocked = ver and out:match("UPDATE_BLOCKED%s+(%S+)") or nil
        done(ver and "update" or "none")
    end)
end

local checking = false
local function start_update()
    if not available_version then
        if checking then
            return
        end
        checking = true
        mp.osd_message("AnimeJaNai: checking for an update...", 30)
        check(function(state, detail)
            checking = false
            if state == "update" then
                start_update()
            elseif state == "failed" then
                mp.osd_message("AnimeJaNai: the update check failed" .. (detail and detail ~= "" and (":\n" .. detail) or ".") ..
                    "\nTry again in a few minutes.", 10)
            else
                mp.osd_message("AnimeJaNai is up to date.", 3)
            end
        end)
        return
    end
    if is_mac then
        start_update_mac()
        return
    end
    if is_appimage then
        mp.osd_message("AnimeJaNai " .. available_version ..
            " is available.\nDownload the new AppImage:\n" .. releases_url, 12)
        return
    end
    mp.osd_message("Installing AnimeJaNai " .. available_version .. " - mpv will close and reopen...", 5)
    -- Detached so it outlives mpv; the updater waits for mpv to exit, applies, then relaunches mpv.
    mp.command_native({
        name = "subprocess",
        args = { updater, "--apply" },
        detach = true,
        playback_only = false,
    })
    mp.add_timeout(1.0, function() mp.command("quit") end)
end

mp.register_script_message("animejanai-update", start_update)
-- macOS has no managed input.conf: the key is bound here (a binding of the user's own wins).
if is_mac then
    mp.add_key_binding("Ctrl+u", "animejanai-update-key", start_update)
end

-- At startup: an update is announced; no update, no connection or no updater stay quiet.
check(function(state)
    if state == "update" then
        msg.info("Update available: " .. available_version)
        local how = is_appimage and "press Ctrl+U for the download link."
                                 or "press Ctrl+U to install."
        mp.osd_message("AnimeJaNai update " .. available_version .. " available - " .. how, 8)
    elseif state == "none" then
        msg.verbose("AnimeJaNai is up to date.")
    end
end)
