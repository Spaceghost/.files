# Follow the desktop theme

The installed 0.2.0.dev0 guide ignores the current Gruvbox theme because its
application stylesheet supplies literal purple colors. The desktop already
exports GTK semantic colors through the user `gtk-3.0/gtk.css`. It updates GTK
settings through its normal desktop integration, but changing the color palette
can leave the GTK theme name unchanged.

Use native GTK color symbols and inherited fonts, with no MBP Intel source-tree
dependency. Reload the user stylesheet on file changes so an existing guide and
settings window update after atomic writes or symlink replacement. Preserve the
last valid stylesheet during incomplete edits. Leave GTK settings under the
desktop's control. Scope application styles to Superhold widgets and clean up
providers and polling when their window is destroyed.

Validate the original purple mismatch and the fix in a private compositor,
including a live dark-to-light palette change in the same window, selected text,
search, and the release overlay. Run the unit suite and build/install a new
versioned prefix. Switch only the Superhold service and keep the previous prefix
and the existing rollback backup; the user authorized this installed correction.
