# Staged radio privacy controller

This directory is an offline staging area only.  Nothing here has changed
`/etc`, OpenRC, rfkill state, wpa_supplicant, or a network connection.

`privacyctl` uses the wpa_supplicant Unix datagram control protocol directly;
every mutating command requires the literal `OK` reply. `off` blocks and then
verifies both radio classes through `/sys/class/rfkill`. `scan` disables saved
networks while blocked, requires a post-request `CTRL-EVENT-SCAN-RESULTS`, and
re-blocks both radios on every error. `connect` selects the permitted saved ID
while blocked, verifies its exact SSID, requires the completed ID and SSID,
clears stale routes, runs DHCP, and then records a supervised session. It is
the only command that leaves Wi-Fi unblocked, and
it accepts only `shmecklebucket` or the separately enabled `iphone-hotspot`
profile.  It does not read, print, save, or edit a PSK.

The OpenRC supervisor polls the control socket against the saved trusted
identity. A disconnect, wrong identity, or wpa_supplicant control failure
removes the session and blocks both radios. Successful association deliberately
leaves Wi-Fi enabled until an explicit `privacyctl off`.

Each supervisor check takes the radio lock without waiting. It skips an active
scan/connect command, whose lock covers the complete authorized transition.
Missing, malformed, or unreadable session state fails off once that command
finishes. Session cleanup errors still trigger radio blocking. The controller
creates its runtime directory privately and refuses symlinked, shared, or
wrong-owner directories; these behaviors are covered by isolated tests.
During a healthy trusted Wi-Fi session it also checks Bluetooth and re-blocks
that radio without disconnecting Wi-Fi. If the Bluetooth block cannot be
verified, the controller fails the session off and attempts to block both.

The staged `72-privacy-rfkill.rules` removes direct user access to `/dev/rfkill`.
Its ordering is deliberate: installed `70-uaccess.rules` adds the `uaccess`
tag, then `73-seat-late.rules` queues elogind's ACL grant. Removing the tag
between those files prevents that grant; placing the override after `73`
would be too late. eudev 3.2.14 supports this tag-removal operation in its
[rule evaluator](https://github.com/eudev-project/eudev/blob/v3.2.14/src/udev/udev-rules.c).
Existing ACLs need separate revocation during activation, as described below.

The root policy file maps a controller profile to an existing numeric
wpa_supplicant network ID and its exact SSID.  Before connecting, the
controller queries the control protocol `LIST_NETWORKS` command and rejects an ID whose configured
SSID differs from the root policy.  `shmecklebucket` must be exactly spelled
that way.  The local iPhone hotspot has deliberately not been named or enabled:
the owner must add its exact spelling and separately uncomment its exact doas
rule.

The `status --json` contract is suitable for a small GUI:

```json
{"wifi":{"soft_blocked":"yes","interface":"wlan0","wpa_state":"UNAVAILABLE"},"bluetooth":{"soft_blocked":"yes"}}
```

It intentionally omits the associated SSID and all credential material.

`root/etc/wpa_supplicant/privacy-policy.conf` is a merge-only policy fragment.
It uses the documented `passive_scan=1` and `p2p_disabled=1` global options;
each permitted network should use `scan_ssid=0`.  It is not included
automatically because the active root-only wpa_supplicant configuration and
its include behavior were intentionally left untouched.

Follow [INSTALL-PLAN.md](INSTALL-PLAN.md) only from a local console with the
recovery path checked.  The plan deliberately leaves the pending boot-off vs
automatic-connect decision at boot-off.
