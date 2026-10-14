local R=dofile(assert(os.getenv('AJ_ROOT'),'set AJ_ROOT')..'/hdr-tools/rife-sync.lua')
local pass,fail=0,0
local function check(n,c,x) if c then pass=pass+1 else fail=fail+1 print('FAIL: '..n..(x and (' -> '..tostring(x)) or '')) end end
local function f(a,b,c) local p,q,out,n=R.choose(a,b,c); return p and (p..'/'..q..'@'..n) or 'nil' end
check('23.976 @144 max2 -> 2/1 (3 refreshes)', f(23.976,144,2)=='2/1@3', f(23.976,144,2))
check('23.976 @143.86 max2', f(23.976,143.856,2)=='2/1@3', f(23.976,143.856,2))
check('23.976 @60 max3 -> 5/2', f(23.976,60,3)=='5/2@1', f(23.976,60,3))
check('23.976 @59.94 max3 -> 5/2', f(23.976,59.94,3)=='5/2@1', f(23.976,59.94,3))
check('23.976 @60 max2 -> 5/4 (2 refreshes)', f(23.976,60,2)=='5/4@2', f(23.976,60,2))
check('23.976 @120 max2 -> 5/3', f(23.976,120,2)=='5/3@3', f(23.976,120,2))
-- No small fraction: the exact ratio (engines with one RIFE run per pair afford it).
check('24000/1001 @165 max2 -> 11011/6400 (4 refreshes)', f(24000/1001,165,2)=='11011/6400@4', f(24000/1001,165,2))
check('24000/1001 @165 max8 -> 11011/1600 (every refresh)', f(24000/1001,165,8)=='11011/1600@1', f(24000/1001,165,8))
check('24 @165 max8 -> 55/8', f(24,165,8)=='55/8@1', f(24,165,8))
check('23.976 @144 max6 -> 6/1', f(23.976,144,6)=='6/1@1', f(23.976,144,6))
check('29.97 @60 max2 -> 2/1', f(29.97,60,2)=='2/1@1', f(29.97,60,2))
check('25 @100 max2 -> 2/1', f(25,100,2)=='2/1@2', f(25,100,2))
check('bad input', f(nil,144,2)=='nil' and f(24,0,2)=='nil')
local conf=[[[global]
backend=TensorRT
display_rate_match=no
[slot_1]
profile_name=a
chain_1_rife=yes
chain_1_rife_factor_numerator=2
chain_1_rife_factor_denominator=1
chain_2_rife=no
chain_2_rife_factor_numerator=2
chain_2_rife_factor_denominator=1
[slot_2]
profile_name=b
chain_1_rife=yes
chain_1_rife_model=426
]]
local out,changed=R.rewrite(conf,5,2)
check('rewrite changed', changed)
check('rife chain updated', out:match('%[slot_1%].-chain_1_rife_factor_numerator=5\nchain_1_rife_factor_denominator=2')~=nil)
check('non-rife chain untouched', out:match('chain_2_rife_factor_numerator=2\nchain_2_rife_factor_denominator=1')~=nil)
check('missing factor lines added', out:match('%[slot_2%].*chain_1_rife_factor_numerator=5')~=nil and out:match('%[slot_2%].*chain_1_rife_factor_denominator=2')~=nil, out)
check('other lines kept', out:match('chain_1_rife_model=426') and out:match('backend=TensorRT'))
local out2,changed2=R.rewrite(out,5,2)
check('idempotent', not changed2 and out2==out)
check('display_rate_match no', not R.display_rate_match(conf))
check('display_rate_match yes', R.display_rate_match(conf:gsub('display_rate_match=no','display_rate_match=yes')))
print(pass..' passed, '..fail..' failed')
os.exit(fail==0 and 0 or 1)
