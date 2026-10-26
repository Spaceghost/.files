# Cat-only media capture

## Status

The user has authorized cat-only capture and private publication under the
rules below. The current implementation detects keyboard/trackpad contact;
it does not identify the cat visually, classify purrs, crop video, or publish
media. This document records the required boundary, not a working feature.
No camera, microphone, stream, or upload was started while documenting it.

## Capture gate

1. Catbed must be active. A camera may then inspect frames locally to look for
   the target cat, but it must not save or transmit unfiltered frames.
2. Require fresh visual confirmation of the target cat before collecting a
   candidate purr window. Keyboard presence can trigger a check, not authorize
   retention. A generic cat classification is not proof of this cat's identity.
3. Stop retention immediately when Catbed ends, the cat is lost, evidence is
   stale, a detector fails, or the privacy decision is uncertain.
4. Keep raw candidate frames and audio only in bounded volatile buffers.
   Prevent raw-media debug dumps, crash dumps, encoder spools, and temporary
   files from bypassing that rule. Account for swap when designing buffers;
   merely allocating Python memory is not a no-disk guarantee.
5. Provide a visible recording indicator and an immediate capture stop control
   that remains independent of input-guard release and remote viewers.

## Video and photos

- Track and crop the target cat before frames reach an encoder, file writer,
  streaming server, thumbnailer, or external service.
- If another subject is present, permit only a crop that excludes that subject.
  If the cat overlaps a person or the crop is uncertain, discard the frame.
- Full-frame output is allowed only with fresh confirmation that the target
  cat is the only subject. Absence of a positive person detection is not itself
  sufficient proof that a person is absent.
- On a missing or rejected frame, output a neutral unavailable frame or stop
  the stream. Never fall back to the unfiltered camera feed.
- Keep live video muted. Do not mux the live microphone into it.
- Apply the same filtering rules to snapshots and preview thumbnails.

## Purr recordings

- Analyze short candidate windows locally. Trim to detected purr intervals.
- Reject speech, non-purr sounds, mixed audio, and uncertain intervals rather
  than assuming source separation removed them perfectly.
- Use padding only if that padding independently passes the same checks.
- Save accepted clips separately from the checkout and ordinary media caches,
  with private filesystem permissions and no unfiltered sidecar recordings.
- Do not claim that the audio or visual classifier can guarantee exclusion of
  every person or human sound. Evaluate false acceptance explicitly before
  allowing unattended publication; default to discarding questionable data.

## Destinations

The private GitHub destination has not been selected. Until it is selected and
verified, uploads remain disabled. Check private visibility and the exact
owner/repository again before each publication batch. Reject public, internal,
unknown, renamed-to-an-unexpected-destination, or inaccessible repositories.
Upload only accepted purr clips and minimal non-sensitive metadata. Never use
the public dotfiles mirror as a staging area or destination for recordings.

Tailnet streaming requires an explicitly configured private listener and
access policy. Do not expose the service on all interfaces, enable Funnel,
or forward a public port. A viewer connects only to filtered output; no raw
camera endpoint should exist as an alternate route.

## Required evaluation before activation

- Cat absent, uncertain identity, multiple animals, and lost/stale tracking.
- People entering at frame edges, hands reaching toward the cat, overlap,
  reflections, changing lighting, and partial occlusion.
- Purring mixed with nearby or distant speech, television, music, fans,
  keyboard sounds, and silence.
- Detector/encoder crashes, slow processing, queue overload, network loss,
  Catbed release, session lock/unlock, and process restarts.
- No raw data in output files, buffers exposed to viewers, logs, temporary
  directories, crash artifacts, or repository history.
- Private-repository checks and tailnet-only access fail closed.

These are outstanding checks. Nothing in the existing Catbed test results
establishes media privacy or authorizes claiming this pipeline is operational.
