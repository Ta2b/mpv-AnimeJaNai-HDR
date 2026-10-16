-- Read-only description of source metadata and the selected inference boundary.
-- Never classify the source from video-out-params (it may already contain TrueHDR).
local M={}
local function known(v) return v~=nil and v~='' and v~='auto' and v~='unknown' end
local function bits(fmt)
    if type(fmt)~='string' then return nil end
    local fixed={nv12=8,nv21=8,rgb24=8,bgr24=8,rgba=8,bgra=8,
        yuv420p=8,yuv422p=8,yuv444p=8,yuvj420p=8,yuvj422p=8,yuvj444p=8,gbrp=8,
        p010=10,p010le=10,p010be=10,p012le=12,p012be=12,p016le=16,p016be=16,
        x2bgr10=10,x2rgb10=10}
    if fixed[fmt] then return fixed[fmt] end
    local n=fmt:match('^yuv%d%d%dp(%d+)[bl]e$') or fmt:match('^gbrp(%d+)[bl]e$')
    n=tonumber(n)
    if n==9 or n==10 or n==12 or n==14 or n==16 then return n end
end
function M.describe(raw,resolved,filters,truehdr)
    raw=type(raw)=='table' and raw or {}
    resolved=type(resolved)=='table' and resolved or {}
    local source,origins={},{}
    for _,k in ipairs({'pixelformat','hw-pixelformat','colormatrix','primaries','gamma',
        'colorlevels','chroma-location','rotate','crop-x','crop-y','crop-w','crop-h'}) do
        if known(raw[k]) then source[k]=raw[k];origins[k]='video-dec-params'
        elseif known(resolved[k]) then source[k]=resolved[k];origins[k]='video-params' end
    end
    local fmt=source['hw-pixelformat'] or source.pixelformat
    local depth=bits(fmt)
    local kind=(source.gamma=='pq' or source.gamma=='hlg' or source.colormatrix=='dolbyvision') and 'hdr'
        or known(source.gamma) and 'sdr' or 'unknown'
    local route='none'
    for _,f in ipairs(type(filters)=='table' and filters or {}) do
        if f.label=='aji' and f.enabled~=false then
            route=f.name=='animejanai-vulkan' and 'rgb24' or f.name=='animejanai' and 'native' or 'unknown'
            break
        end
    end
    local boundary
    if route=='rgb24' then
        boundary='Inference : RGB 8 bits SDR'
        if kind=='hdr' then boundary=boundary..' | source HDR non admissible sur cette voie'
        elseif depth and depth>8 then boundary=boundary..' | quantification '..depth..' -> 8 bits'
        elseif not depth then boundary=boundary..' | profondeur source inconnue' end
    elseif route=='native' then
        boundary='Inference : voie native YUV/RGB FP16 | profondeur effective selon format negocie'
    elseif route=='none' then boundary='Inference : inactive'
    else boundary='Inference : format de traitement inconnu' end
    if truehdr then boundary=boundary..' | balise HDR aval active (ne decrit pas la source)' end
    local function show(k) return tostring(source[k] or 'inconnu') end
    local line='Source avant filtres : '..tostring(fmt or 'inconnu')..' | '..tostring(depth or '?')
        ..' bits/composante | matrice='..show('colormatrix')..' | primaires='..show('primaries')
        ..' | transfert='..show('gamma')..' | plage='..show('colorlevels')..' | chroma='..show('chroma-location')
        ..' | rotation='..show('rotate')
    if source['crop-w'] and source['crop-h'] then
        line=line..' | crop='..show('crop-w')..'x'..show('crop-h')..'+'..show('crop-x')..'+'..show('crop-y')
    end
    return {schema=1,source=source,origins=origins,component_bits=depth,kind=kind,route=route,
        source_line=line,boundary_line=boundary,gamut_preservation='not-qualified-by-metadata',
        quantization=route=='rgb24' and '8-bit RGB boundary' or 'see negotiated format'}
end
return M
