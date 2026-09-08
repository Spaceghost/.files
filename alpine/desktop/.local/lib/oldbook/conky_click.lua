-- Native desktop-surface clicks; ordinary applications stay above these cards.
local cards = {scripture = true, witness = true, ghost = true, gallery = true}
local history_link

function conky_oldbook_history(x, width, height)
    history_link = {x = tonumber(x), width = tonumber(width), height = tonumber(height)}
end

function conky_oldbook_click(event)
    if event.type ~= 'button_down' or event.button ~= 'left' then
        return false
    end
    local identifier = (conky_config or ''):match('([^/]+)%.conf$')
    if not cards[identifier] then
        return false
    end
    if identifier == 'scripture' and history_link
            and type(event.x) == 'number' and type(event.y) == 'number'
            and event.x >= history_link.x and event.x < history_link.x + history_link.width
            and event.y >= 0 and event.y < history_link.height then
        identifier = 'scripture-history'
    end
    -- HOME is expanded by the shell inside quotes; the only argument is allowlisted.
    os.execute('"$HOME/.local/bin/oldbook-conky-click" ' .. identifier ..
               ' >/dev/null 2>&1 &')
    return true
end
