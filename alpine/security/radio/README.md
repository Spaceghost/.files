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
