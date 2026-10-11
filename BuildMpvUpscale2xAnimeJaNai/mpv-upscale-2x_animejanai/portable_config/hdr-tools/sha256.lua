-- SHA-256 in plain Lua with the LuaJIT `bit` or Lua 5.2 `bit32` library.
-- Returns an uppercase hex digest, or nil when no bit library is available.
local ok, bit = pcall(require, 'bit')
if not ok then ok, bit = pcall(require, 'bit32') end
if not ok or not bit then bit = rawget(_G, 'bit32') or rawget(_G, 'bit') end
if not bit then return function() return nil end end

local band, bor, bxor, bnot = bit.band, bit.bor, bit.bxor, bit.bnot
local rshift, lshift = bit.rshift, bit.lshift
local MASK = 0xffffffff
local function u32(x) return band(x, MASK) end
local function rrot(x, n) return bor(rshift(x, n), lshift(x, 32 - n)) end

local K = {
 0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
 0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
 0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
 0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
 0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
 0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
 0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
 0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2}

return function(msg)
    local len = #msg
    local bits = len * 8
    msg = msg .. '\128' .. string.rep('\0', (55 - len) % 64)
    local hi = math.floor(bits / 4294967296)
    local lo = bits % 4294967296
    for _, v in ipairs({hi, lo}) do
        msg = msg .. string.char(math.floor(v / 16777216) % 256, math.floor(v / 65536) % 256,
                                 math.floor(v / 256) % 256, v % 256)
    end
    local h = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19}
    local w = {}
    for chunk = 1, #msg, 64 do
        for i = 0, 15 do
            local a, b, c, d = msg:byte(chunk + i * 4, chunk + i * 4 + 3)
            w[i] = u32(a * 16777216 + b * 65536 + c * 256 + d)
        end
        for i = 16, 63 do
            local s0 = bxor(rrot(w[i-15], 7), rrot(w[i-15], 18), rshift(w[i-15], 3))
            local s1 = bxor(rrot(w[i-2], 17), rrot(w[i-2], 19), rshift(w[i-2], 10))
            w[i] = u32(w[i-16] + s0 + w[i-7] + s1)
        end
        local a, b, c, d, e, f, g, hh = h[1], h[2], h[3], h[4], h[5], h[6], h[7], h[8]
        for i = 0, 63 do
            local S1 = bxor(rrot(e, 6), rrot(e, 11), rrot(e, 25))
            local ch = bxor(band(e, f), band(bnot(e), g))
            local t1 = u32(hh + S1 + ch + K[i+1] + w[i])
            local S0 = bxor(rrot(a, 2), rrot(a, 13), rrot(a, 22))
            local maj = bxor(band(a, b), band(a, c), band(b, c))
            local t2 = u32(S0 + maj)
            hh, g, f, e, d, c, b, a = g, f, e, u32(d + t1), c, b, a, u32(t1 + t2)
        end
        h[1], h[2], h[3], h[4] = u32(h[1] + a), u32(h[2] + b), u32(h[3] + c), u32(h[4] + d)
        h[5], h[6], h[7], h[8] = u32(h[5] + e), u32(h[6] + f), u32(h[7] + g), u32(h[8] + hh)
    end
    local out = {}
    for i = 1, 8 do out[i] = string.format('%08X', h[i] % 4294967296) end
    return table.concat(out)
end
