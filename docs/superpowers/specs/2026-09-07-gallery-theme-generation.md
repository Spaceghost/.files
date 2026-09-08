# Ghost Gallery theme generation

The gallery can paint within existing themes but cannot create another theme.
Add random and phrase/title actions which design a reusable named artwork
collection, then generate and select one matching debut wallpaper. Application
configuration remained independent in the original implementation. This is
superseded by the user's requirement that every desktop theme be complete:
generated themes must also supply application styling. A descriptor and debut
wallpaper alone are not a finished desktop theme.

Use the existing logged-in Codex CLI with strict structured output for name,
palette, art direction and debut scene. Disable tools for this text-only phase.
Validate fields and colors, derive a unique safe filename locally, and exclusively
create the descriptor. Keep the existing generation lock across design and image
creation so repeated clicks cannot spend simultaneous requests. Native image
validation, activation and pending-checkpoint recovery remain the same. Include a
new descriptor in the exact-path local image checkpoint after verifying its hash.
Previously committed descriptors and unrelated user edits are never included.

The popup accepts cancellation and passes phrases as literal arguments, never
shell fragments. Theme failures notify the user and leave the current image.
Image failures retain the new collection for a later named-generation request.

Validation covers malformed definitions, directory symlinks, unique collection
creation, cancelled and literal phrase input, debut scene propagation, and real
isolated Fossil preservation with unrelated edits. Run the full desktop suite,
exercise native random theme generation, and capture the gallery launcher.
Recovery: restore these feature files from the parent Fossil check-in; generated
art and descriptors can remain safely in the catalog or be removed individually.
