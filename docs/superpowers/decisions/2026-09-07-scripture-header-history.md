# Scripture header History link

The desktop History action belongs on the Scripture heading line. The separate
GTK button beside the Bible search bar did not receive that bar's palette rules
and was detached from the reading card it opens.

The shared Conky renderer places a text link at the right end of the existing
heading, using the card's font and wallpaper-adjusted accent. It replaces the
horizontal rule to keep that rule out of the label. Applying this at render time
also updates existing generated theme templates without changing their fonts,
placements, disabled cards, or reading content. The search bar retains its search
and reflections gestures and hourly tick.

The link's click rectangle is passed to the native Lua mouse hook through
`lua_startup_hook`; configuration globals are not assumed to share the hook's Lua
state. Both the text position and click rectangle use the same generated geometry.
Only a left press inside that rectangle opens History. Other reading-card presses
retain their existing actions. The History subprocess is launched without holding
the card lock for the reader's lifetime.

Conky's [Lua API](https://conky.cc/lua) and
[mouse hook documentation](https://conky.cc/config_settings) describe the native
hooks used here. Native verification, screenshots, deployment details and recovery
are recorded in [the header evidence](../../../alpine/verification/scripture-header/README.md).
