# Activation plan — do not run remotely

This plan is for the owner to review and perform from a local console.  The
currently staged default is **boot-off with explicit scan/connect**.  It does
not enable automatic discovery or reconnection.

Before changing anything, keep a known working wired or local-console recovery
path.  Record the current files and OpenRC membership, then use a temporary
root shell or separate console to test recovery.  Do not expose the active
wpa_supplicant file or its PSK in terminal scrollback, Fossil, or this tree.

1. Install the staged files with root ownership and these modes:

   | Staged source | Target | Mode |
   | --- | --- | --- |
   | `root/usr/local/sbin/privacyctl` | `/usr/local/sbin/privacyctl` | `0750` |
   | `root/etc/privacyctl/profiles` | `/etc/privacyctl/profiles` | `0600` |
   | `root/etc/doas.d/privacyctl.conf` | `/etc/doas.d/privacyctl.conf` | `0400` |
   | `root/etc/init.d/radio-off` | `/etc/init.d/radio-off` | `0755` |
   | `root/etc/init.d/privacyctl-supervisor` | `/etc/init.d/privacyctl-supervisor` | `0755` |
   | `root/etc/elogind/system-sleep/95-radio-off` | same path | `0755` |

   Create `/etc/privacyctl` as `root:root`, `0700`.  Verify every installed
   file has `root:root`; do not make the profile policy writable by `jack`,
   wheel, or a service account.

2. In a root-only editor, find the saved wpa_supplicant network ID for the
   existing `shmecklebucket` entry.  Put only its ID and the literal SSID in
   `/etc/privacyctl/profiles`, for example
   `profile|shmecklebucket|0|shmecklebucket`.  The numeric ID is illustrative;
   use the actual local ID.  Merge the three non-secret settings in
   `privacy-policy.conf` into the active root-only wpa_supplicant config and
   set `scan_ssid=0` inside each allowed network block.  Never copy the
   network block or PSK into this repository.

   Ensure the active configuration has a root-accessible control socket for
   the existing service (normally `ctrl_interface=DIR=/run/wpa_supplicant`).
   `privacyctl` opens the fixed root control socket directly; the GUI only
   calls the controller through exact doas rules and must not read that socket.
   After a verified association, the controller flushes stale IPv4 routes and
   global addresses then uses the fixed `udhcpc` invocation. For the hotspot it
   also flushes global IPv6 routes/addresses before DHCP, preventing inherited
   static IPv6 from the home profile. Confirm the local DHCP lease succeeds.

   At staging time, `/run/wpa_supplicant` existed but was empty and the
   read-only `doas wpa_cli -i wlan0 status` check exited 255.  Treat a zero-exit
   control-socket status check as a prerequisite; do not activate the
   controller until it passes.

3. Do **not** add the iPhone profile or doas rule until its exact local SSID is
   known.  Then add one four-field line using `iphone-hotspot`, its existing
   numeric ID, and the exact spelling; verify `wpa_cli list_networks` shows the
   same spelling; then separately enable the commented exact doas rule.  No
   wildcard SSID, BSSID-only policy, or guessed iPhone name is acceptable.

4. Add `radio-off` to the OpenRC `boot` runlevel and
   `privacyctl-supervisor` to the default runlevel. Its dependencies place the
   block before networking/wpa_supplicant and the supervisor after
   wpa_supplicant. Leave saved credentials root-only and automatic selection
   disabled until an explicit `privacyctl connect` call selects one permitted
   saved ID.

5. This host boots GRUB. In a root-only editor append exactly
   `rfkill.default_state=0` to `GRUB_CMDLINE_LINUX_DEFAULT` in
   `/etc/default/grub`, then regenerate `/boot/grub/grub.cfg` with the locally
   installed `grub-mkconfig`. Check `/proc/cmdline` and the running kernel’s
   rfkill parameter after reboot. This complements OpenRC; it does not prove
   that firmware or hardware emitted no RF before Linux takes control.

6. Validate first on the local console: `doas privacyctl status --json`,
   `doas privacyctl off`, then `doas privacyctl scan`.  Confirm Wi-Fi is
   blocked when the scan command exits, including after a deliberately failed
   wpa_cli request.  Only then test `doas privacyctl connect shmecklebucket`.
   Restore with `doas privacyctl off` before leaving the console.

7. Install the staged elogind hook at `/etc/elogind/system-sleep/95-radio-off`.
   This host’s elogind binary explicitly loads that directory and invokes the
   hook before sleep and after resume. Test that both radios remain soft-blocked
   after wake.

## Limits of this design

An SSID is not evidence of location.  Neither the allowlist, passive scans,
nor a saved-network check creates geofencing.  A software policy cannot prove
physical RF silence before the operating system, during a hardware fault, or
when a hard/firmware radio state differs from rfkill.  `brcmfmac` on this host
does not advertise scan-MAC randomization, so this staging makes no such
claim.  Intentional scans and associations can be detectable by nearby radio
equipment.
