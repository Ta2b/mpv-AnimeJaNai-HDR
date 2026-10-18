-- Shared profile HDR routing. This never retags source/native SDR surfaces.
-- The conversion is a global setting (docs/CONTRAT-PROFILS-V2.md): a profile never
-- overrides it. route() returns what the launcher published for the active profile.
local M={}
function M.route(mp,hardware)
    local configured=mp.get_property_native('user-data/animejanai-pipeline-configured')
    if type(configured)=='table' then return configured end
    local slot=tonumber((mp.get_property_native('user-data/animejanai-active-slot')))
    local conf=hardware and hardware.conf or os.getenv('ANIMEJANAI_CONF') or mp.command_native({'expand-path','~~/../animejanai/animejanai.conf'})
    local f=conf and io.open(conf,'rb');if not f then return nil end
    local text=f:read('*a');f:close()
    if not slot then slot=tonumber(text:match('default_slot%s*=%s*(%d+)')) or 0 end
    if slot<1 or slot>9 then return nil end
    local source=mp.get_property_native('video-params') or {}
    local stages=dofile(mp.command_native({'expand-path','~~/hdr-tools/interpolation-stages.lua'}))
    return stages.resolve(text,slot,source.w,source.h,tonumber((mp.get_property_native('container-fps'))))
end
-- Kept for callers that pass a route: the global settings apply unchanged.
function M.options(base,route) return base end
return M
