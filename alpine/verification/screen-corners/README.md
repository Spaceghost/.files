# Screen corner verification

SwayFX 0.6-r3 adds a final 20-logical-pixel output mask after the entire scene
and software cursors. It locks out direct scanout and hardware cursor planes.
The environment setting is opt-in in the compositor and defaults to 20 in the
Space Ghost HOME launcher. No usable-area or input-region changes are made.

The exact signed APK was verified and its extracted executable SHA-256 matches
the tested payload: 9476e4f292dc092cd42c2a984cdf9857f4ad248c28311708704049c0fce3be64.
The previous unmodified binary fails the white-background corner assertion.
The packaged binary passes background, fullscreen, later overlay, a confirmed
visible virtual pointer moved into a corner, repeated redraw, scale, rotation,
resize, reload and session-lock tests in a private headless compositor.
The test checks pixels wholly outside the circle, allowing partially covered
antialiased boundary pixels independently of output rotation.

The final binary also passes the existing native hover suite and all 23 bottom
titlebar checks with masks enabled. Both SwayFX and stock-Sway configurations
validate. Mapped feature checks passed except one three-second deployment status
check timed out under load; all 20 deployment checks passed on the unchanged
retry. Both logs are retained. Compilation succeeded; its wrapper was interrupted
during packaging. Resuming the normal abuild rootpkg step produced the signed APK.

Installation changed only SwayFX, retaining all other 1,120 package identities.
The live launcher is a symlink into the tracked HOME overlay, so its new startup
setting is already in place. The existing compositor process remains running
its old executable; activation requires logout/login. Physical DRM scanout,
GPU-reset recovery and physical frame rate have not been exercised in that new
session. Headless evidence must not be described as a physical-screen test.

Recovery: start `SPACEGHOST_SCREEN_CORNER_RADIUS=0 oldbook-sway` for square output
corners, or `OLDBOOK_STOCK_SWAY=1 oldbook-sway` for stock Sway. The previous signed
APK remains in the Fossil archive and the previous personal repository is retained.

The signed, offline 784-package closure simulation passes with the new desktop
r1 and SwayFX r3 identities. This is a solver check, not a new root installation.
The local edge/personal repository is updated; its previous contents remain at
`/var/lib/cascadia/repositories/apk/edge/personal-before-screen-corners`.
