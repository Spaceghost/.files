-- Native desktop-surface clicks; ordinary applications stay above these cards.
local cards = {scripture = true, witness = true, ghost = true, gallery = true}

function conky_oldbook_click(event)
    if event.type ~= 'button_down' or event.button ~= 'left' then
        return false
    end
    local identifier = (conky_config or ''):match('([^/]+)%.conf$')
    if not cards[identifier] then
        return false
    end
    -- HOME is expanded by the shell inside quotes; the only argument is allowlisted.
    os.execute('"$HOME/.local/bin/oldbook-conky-click" ' .. identifier ..
               ' >/dev/null 2>&1 &')
    return true
end
