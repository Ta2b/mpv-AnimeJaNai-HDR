-- Pure media-control state. Automatic holds never own the user's pause intent.
local M = {}
local State = {}; State.__index = State
function M.new(callbacks)
    return setmetatable({cb=callbacks, user_paused=callbacks.get_pause(),
        holds={}, generation=1, loaded=false, seeking=false, error=nil,
        override=false, pending_pause=nil, transition=0}, State)
end
function State:snapshot()
    local owners, preparation, refill, blocking = {}, false, false, false
    for owner, hold in pairs(self.holds) do
        owners[#owners+1]=owner
        blocking=blocking or hold.blocking
        preparation=preparation or hold.kind=='preparation'
        refill=refill or hold.kind=='refill'
    end
    table.sort(owners)
    local state, reason
    if self.seeking then state,reason='SEEK','seek-in-progress'
    elseif self.error then state,reason='ERREUR',self.error
    elseif self.user_paused then state,reason='PAUSE_UTILISATEUR','user-pause'
    elseif preparation then state,reason='PREPARATION',table.concat(owners,',')
    elseif refill then state,reason='REMPLISSAGE',table.concat(owners,',')
    elseif not self.loaded then state,reason='PREPARATION','waiting-for-file'
    else state,reason='LECTURE','ready' end
    return {version=1,state=state,reason=reason,generation=self.generation,
        user_paused=self.user_paused,automatic_pause=blocking and not self.override,
        effective_pause=self.cb.get_pause(),manual_override=self.override,
        holders=owners,transition=self.transition}
end
function State:publish()
    local value=self:snapshot()
    if value.state~=self.last_state or value.reason~=self.last_reason then
        self.transition=self.transition+1
        self.last_state,self.last_reason=value.state,value.reason
        value.transition=self.transition
    end
    self.cb.publish(value)
end
function State:has_blocking_hold()
    for _,hold in pairs(self.holds) do if hold.blocking then return true end end
    return false
end
function State:apply()
    local wanted=self.user_paused or (self:has_blocking_hold() and not self.override)
    if self.cb.get_pause()~=wanted then
        self.pending_pause=wanted
        self.cb.set_pause(wanted)
    end
    self:publish()
end
function State:observe_pause(value)
    if value==nil then return end
    if self.pending_pause~=nil and value==self.pending_pause then
        self.pending_pause=nil
    else
        self.pending_pause=nil
        self.user_paused=value
        if not value and self:has_blocking_hold() then self.override=true end
    end
    -- An observed manual unpause wins; never reassert a hold here.
    self:publish()
end
function State:user_pause(value)
    self.pending_pause=nil
    self.user_paused=value
    if not value and self:has_blocking_hold() then self.override=true end
    self:apply()
end
function State:hold(owner, kind, generation, blocking)
    if generation~=self.generation or owner=='' or
       (kind~='preparation' and kind~='refill') then return false end
    self.holds[owner]={kind=kind,blocking=blocking~=false}
    self.error=nil
    self:apply(); return true
end
function State:release(owner, generation)
    if generation~=self.generation then return false end
    self.holds[owner]=nil
    if not next(self.holds) then self.override=false end
    self:apply(); return true
end
function State:fail(owner, reason, generation)
    if generation~=self.generation then return false end
    self.holds[owner]=nil; self.error=reason
    if not next(self.holds) then self.override=false end
    self:apply(); return true
end
function State:start_file()
    self.generation=self.generation+1
    self.holds={}; self.error=nil; self.loaded=false; self.seeking=false
    self.override=false
    self:apply()
end
function State:end_file(reason)
    self:start_file()
    self.error=reason
    self:publish()
end
function State:file_loaded()
    self.loaded=true; self:publish()
end
function State:seek(value)
    self.seeking=value; self:publish()
end
return M
