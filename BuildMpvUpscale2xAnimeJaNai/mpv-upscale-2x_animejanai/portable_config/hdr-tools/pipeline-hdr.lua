-- Shared profile HDR routing. This never retags source/native SDR surfaces.
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
function M.options(base,route)
    if type(route)=='table' and not route.hdr_stage_controlled and not base.conversion_in_profiles then return base end
    local effective={};for k,v in pairs(base) do effective[k]=v end
    effective.hdr_conversion=false;effective.hdr_backend='none'
    local stage=type(route)=='table' and route.hdr;if not stage then return effective end
    if stage.method=='mpv' and stage.runtime=='gpu-next' or stage.method=='nvidia-truehdr' and stage.runtime=='rtx-video' then
        local values=stage.options or {}
        local bounds={contrast={0,200},saturation={0,200},middle_gray={10,100},paper_white={80,400},highlights={0,100},vibrance={0,80}}
        for key,limits in pairs(bounds) do if values[key] then
            local n=tonumber(values[key]);if not n or n%1~=0 or n<limits[1] or n>limits[2] then return effective end
        end end
        if values.mpv_truehdr_look and values.mpv_truehdr_look~='yes' and values.mpv_truehdr_look~='no' then return effective end
        effective.hdr_conversion=true;effective.hdr_backend=stage.method=='mpv' and 'mpv' or 'rtx'
        for key,target in pairs({contrast='rtx_contrast',saturation='rtx_saturation',middle_gray='rtx_middle_gray',paper_white='paper_white'}) do
            if values[key] then effective[target]=tonumber(values[key]) end
        end
        if values.mpv_truehdr_look then effective.mpv_truehdr_look=values.mpv_truehdr_look=='yes' end
        for _,key in ipairs({'highlights','vibrance'}) do if values[key] then effective[key]=(tonumber(values[key]) or 0)/100 end end
    end
    return effective
end
return M
