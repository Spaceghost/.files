# Workspace typography verification

The signed r5 library passes six real Waybar states in Spaceghost and Gruvbox:
workspace 1 active, workspace 2 active, and a renamed workspace with Unicode and
literal markup characters. The inspector checks every UTF-8 byte's effective
weight and foreground color. Screenshots use synthetic windows only.

Active number/name: bold 700 and bright theme color. Inactive number: bold 700;
name: normal 400. Process text: normal 400 and the secondary theme color.

The native GTK fixture passed 38 checks including label replacement, newly
packed buttons and both cleanup orders. Four existing native tooltip callbacks
also passed on the exact signed library. See the package verification metadata
for source, build, installation and archive hashes.

Reproduce the real Waybar checks from the repository root:

```sh
alpine/packages/waybar-art/verify-workspaces-headless --module /usr/lib/waybar/oldbook-art.so --output /tmp/workspace-emphasis-new
```
