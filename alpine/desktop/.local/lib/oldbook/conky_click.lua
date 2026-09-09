-- Native desktop-surface clicks; ordinary applications stay above these cards.
local cards = {scripture = true, witness = true, ghost = true, gallery = true, rice = true}
local history_link
local rice_link

function conky_oldbook_history(x, width, height)
    history_link = {x = tonumber(x), width = tonumber(width), height = tonumber(height)}
end

function conky_oldbook_rice(x, width, height)
    rice_link = {x = tonumber(x), width = tonumber(width), height = tonumber(height)}
end

local function inside(link, event)
    return link ~= nil and type(event.x) == 'number' and type(event.y) == 'number'
        and event.x >= link.x and event.x < link.x + link.width
        and event.y >= 0 and event.y < link.height
end

function conky_oldbook_click(event)
    local identifier = (conky_config or ''):match('([^/]+)%.conf$')
    if not cards[identifier] then
        return false
    end
    if event.type == 'mouse_scroll' then
        -- Only the rice list has pages to turn. A wheel event without a
        -- direction is left alone rather than guessed at, so a compositor that
        -- reports the wheel differently simply does nothing here; the list is
        -- still reachable a click at a time.
        if identifier ~= 'rice' or type(event.direction) ~= 'string' then
            return false
        end
        identifier = (event.direction == 'up' or event.direction == 'left')
            and 'rice-page-up' or 'rice-page-down'
    elseif event.type ~= 'button_down' then
        return false
    elseif event.button == 'right' then
        -- Only Scripture and the rice list keep somewhere to step back to.
        if identifier == 'rice' then
            identifier = 'rice-back'
        elseif identifier ~= 'scripture' then
            return false
        else
            identifier = 'scripture-previous'
        end
    elseif event.button == 'middle' then
        -- Ticking an entry off is the rice list's alone.
        if identifier ~= 'rice' then
            return false
        end
        identifier = 'rice-tried'
    elseif event.button ~= 'left' then
        return false
    elseif identifier == 'scripture' and inside(history_link, event) then
        identifier = 'scripture-history'
    elseif identifier == 'rice' and inside(rice_link, event) then
        identifier = 'rice-try'
    end
    -- HOME is expanded by the shell inside quotes; the only argument is allowlisted.
    os.execute('"$HOME/.local/bin/oldbook-conky-click" ' .. identifier ..
               ' >/dev/null 2>&1 &')
    return true
end
