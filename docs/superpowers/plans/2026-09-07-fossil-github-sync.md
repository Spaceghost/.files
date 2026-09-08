# Fossil GitHub and cross-host replay plan

1. Audit committed/pending files, remote branches, credentials and Tailscale.
2. Configure the incremental mirror outside HOME's source overlay. Add a
   publisher that exports then pushes only `alpine-oldbook`, with no force.
3. Test and document GitHub-to-Fossil bootstrap and its identity/archive limits.
4. Add consistent public-copy scrubbing; retain private backup semantics.
5. Provide a conservative Bazzite replay profile with backup/rollback and
   explicit runtime prerequisites, sharing the existing desktop assets.
6. Capture installed package changes and checkpoint reviewed source paths.
7. Publish and verify the Git branch; preserve a full Fossil artifact backup
   separately. Report any authentication or unavailable-host verification.
