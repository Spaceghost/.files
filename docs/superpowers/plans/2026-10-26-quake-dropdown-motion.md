# Quake-style dropdown implementation plan

1. Add failing configuration and geometry contract tests for enabled native
   animation, fade workspace switching, the dropdown mark, bottom-only radius,
   and full usable output width.
2. Extend the pinned SwayFX animation patch with marked-dropdown settings, a
   `dropdown toggle` runtime command, vertical reveal/dismiss state, reversible
   transitions, bottom-only corner radii, and no dropdown shadow.
3. Extend the headless verifier to prove downward reveal, upward dismissal,
   mid-flight reversal, and square-top/rounded-bottom clipping.
4. Route `oldbook-dropdown` through the native command with a non-fatal fallback
   for older running compositors, and preserve existing sticky/process behavior.
5. Build the pinned source offline as r5, verify its signature and checksums,
   archive the exact APK, install without restarting the current session, and
   rerun focused configuration, integration, and packaged-binary checks.
