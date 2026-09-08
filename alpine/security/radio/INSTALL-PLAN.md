# Radio activation plan

## Current activation state

Permission preparation and Bluetooth-only soft blocking are installed on this
host. The reviewed permission helper is
installed at `/usr/local/libexec/oldbook-radio/install` (`root:root`, `0750`),
with its matching `72-privacy-rfkill.rules` beside it and in `/etc/udev/rules.d/`
(`0644`). The private journal is
`/var/lib/oldbook/radio-permissions/attempt-0huvvd1q`.

Independent verification confirmed `/dev/rfkill` mode `0644`, no ACL or
`uaccess` tag, Jack read access with write-open denied, and root write access.
During the initial permission step, both radio states, Wi-Fi association and
addresses were preserved; route
comparison excluded only `expires` fields. Waybar's existing status handle and
both wpa_supplicant handles were read-only. See
[permissions-verification.json](permissions-verification.json) for hashes and
sanitized evidence. No controller, radio OpenRC service, sleep hook, profile,
WPA or DHCP change has been activated.

The inert `oldbook-radio-runtime=0.1.0-r0` APK has since installed the CLI,
fourteen Python modules and both private DHCP helpers. Only one package was
added; all nine before/after host-network comparison sections matched, including
the same WPA/DHCP process identities. The package has no activation scripts,
profiles, doas grants, OpenRC services or sleep hooks. See the
[runtime package instructions](../../packages/privacyctl-runtime/README.md).
Trusted profiles, service startup, sleep integration and WPA/DHCP/resolver
ownership remain unactivated.

The subsequent `71-privacy-bluetooth-off.rules` preparation software-blocked
Bluetooth while preserving WLAN radio state, association, addresses and routes.
The helper and its recovery journal were independently checked; see
[bluetooth-verification.json](bluetooth-verification.json) and the separate
[Bluetooth installation/recovery instructions](BLUETOOTH.md). No live unblock
or rollback was used to verify persistence; reboot and suspend remain untested.

## Remaining controller activation

Perform network-changing activation from a local console with recovery ready.
The staged default is **boot-off with explicit scan/connect**. It does not
enable automatic discovery or reconnection. The installed permissions and
Bluetooth policy do not make the full controller ready for unattended networking.
The runtime files are installed; controller policy and service activation remain
staged. Current source-hashed component and
combined checks are recorded in [owner-verification.json](owner-verification.json);
the older controller report covers historical helpers only. Combined failure
tests now pass; see [fault-verification.json](fault-verification.json).
The [isolated packet-policy proof](../firewall/radio-policy-verification.json)
also passes. Live policy decisions, remaining [orphan recovery acceptance](ORPHAN-RECOVERY.md),
OpenRC startup and the migration installer remain unfinished. This is the activation
sequence to implement and verify, not a completed unattended installer.

Before changing anything, keep a known working wired or local-console recovery
path.  Record the current files and OpenRC membership, then use a temporary
root shell or separate console to test recovery.  Do not expose the active
wpa_supplicant file or its PSK in terminal scrollback, Fossil, or this tree.

1. For a rebuild, install the reviewed inert runtime APK first. This host already
   has `oldbook-radio-runtime=0.1.0-r0`; do not manually replace its CLI, library
   or helper files. The table records their installed contract together with
   the policy/service files still awaiting activation:

   | Staged source | Target | Mode |
   | --- | --- | --- |
   | `root/usr/local/sbin/privacyctl` | `/usr/local/sbin/privacyctl` | `0750` |
   | `root/usr/local/lib/privacyctl_runtime/*.py` | `/usr/local/lib/privacyctl_runtime/` | `0644` |
   | `root/usr/local/libexec/privacyctl-dhcp-launch` | `/usr/local/libexec/privacyctl-dhcp-launch` | `0750` |
   | `root/usr/local/libexec/privacyctl-dhcp-event` | `/usr/local/libexec/privacyctl-dhcp-event` | `0750` |
   | `root/etc/privacyctl/profiles` | `/etc/privacyctl/profiles` | `0600` |
   | `root/etc/doas.d/privacyctl.conf` | `/etc/doas.d/privacyctl.conf` | `0400` |
   | `root/etc/init.d/radio-off` | `/etc/init.d/radio-off` | `0755` |
   | `root/etc/init.d/privacyctl-supervisor` | `/etc/init.d/privacyctl-supervisor` | `0755` |
   | `root/etc/elogind/system-sleep/95-radio-off` | same path | `0755` |
   | `root/etc/udev/rules.d/72-privacy-rfkill.rules` | same path | `0644` |

   Use [STAGED-MANIFEST.tsv](STAGED-MANIFEST.tsv) for the complete source list.
   APK installs the CLI, library and both helpers together; their fixed paths
   are part of the verified contract. The rfkill permission rule is also already
   installed through its separate preparation. Keep implementation directories root-owned,
   mode `0755`, with no writable ancestors controlled by another user.
   Create `/etc/privacyctl` as `root:root`, `0700`.  Verify every installed
   file has `root:root`; do not make the profile policy writable by `jack`,
   wheel, or a service account.

   Create root-private `/etc/privacyctl/ipv6.json` with explicit entries for
   each enabled profile, including an empty hotspot profile when appropriate.
   Its format is in [OWNER-SERVICE.md](OWNER-SERVICE.md). Missing policy is
   rejected before unblock. Keep actual network addresses out of Fossil.

   The controller creates `/run/privacyctl` as `root:root`, `0700` before
   listening on its root-only socket. It blocks and clears stale session
   authorization at startup. A surviving `lease-dirty` marker refuses new
   connections until verified recovery; never delete it simply to reconnect.

2. Confirm the exact trusted home SSID before enabling its policy. The profile
   name `shmecklebucket` is a controller alias, not proof of the saved SSID.
   In a root-only editor, find the corresponding saved wpa_supplicant network
   ID. Put only its ID and the confirmed literal SSID in
   `/etc/privacyctl/profiles`, for example
   `profile|shmecklebucket|0|shmecklebucket`.  The numeric ID is illustrative;
   use the actual local ID and confirmed spelling. Merge the non-secret settings in
   `privacy-policy.conf` into the active root-only wpa_supplicant config and
   set `scan_ssid=0` inside each allowed network block. Start every saved
   network disabled until the controller selects it. Never copy a network
   block or PSK into this repository.

   Ensure the active configuration has a root-accessible control socket for
   the existing service (normally `ctrl_interface=DIR=/run/wpa_supplicant`).
   `privacyctl` opens the fixed root control socket directly; the GUI only
   calls the controller through exact doas rules and must not read that socket.
   Adding that socket disrupts association; do not send a casual reload or
   restart networking. Follow the blocked, exact-backup transition in
   [NETWORK-MIGRATION.md](NETWORK-MIGRATION.md).

   Establish exactly one DHCP owner during that transition. Disable automatic
   WLAN DHCP/static provisioning in ifupdown-ng while preserving unrelated
   interfaces. While blocked, stop only the identity-verified legacy client and
   its hooks, and remove only verified legacy state being transferred. Its
   release-on-exit behavior must be covered by the migration/recovery check.

   The persistent owner keeps one foreground `udhcpc -f -n` client through
   acquisition and renewal. It acknowledges a lease only after verified WPA
   identity and native address/DNS application. Profile transitions remove only
   recorded resources; returning home explicitly reapplies its static IPv6.
   Do not broadly flush interface state or reintroduce a one-shot client.
   Complete and test orphan recovery before unattended service activation.

   Prepare the reviewed libc-only resolver subscriber policy and deliberate
   `resolvconf -u` takeover separately. The installed compatibility APK alone
   has not taken ownership of DNS. Prove renewal and offered-DNS authorization
   against the packet gate and OpenSnitch without broadening live grants.

   At staging time, `/run/wpa_supplicant` existed but was empty and the
   read-only `doas wpa_cli -i wlan0 status` check exited 255.  Treat a zero-exit
   control-socket status check as a prerequisite; do not activate the
   controller until it passes.

3. Do **not** add the iPhone profile or doas rule until its exact local SSID is
   known.  Then add one four-field line using `iphone-hotspot`, its existing
   numeric ID, and the exact spelling; verify `wpa_cli list_networks` shows the
   same spelling; then separately enable the commented exact doas rule.  No
   wildcard SSID, BSSID-only policy, or guessed iPhone name is acceptable.

4. Revoke the existing per-user rfkill ACL after installing the udev rule.
   The rule must sort after `70-uaccess.rules` and before `73-seat-late.rules`:
   the first adds the tag and the second queues elogind's user-access grant.
   A rule loaded after `73` cannot undo that already queued grant.

   The installed helper has already completed this step on this host. These
   manual equivalents are retained for rebuilding elsewhere; no repeat is
   needed for the verified installation. Python is already a controller
   dependency, so no extra ACL package is needed:

   ```sh
   doas python3 - <<'PY'
   import errno, os
   try:
       os.removexattr('/dev/rfkill', 'system.posix_acl_access')
   except OSError as error:
       if error.errno not in (errno.ENODATA, errno.ENOTSUP):
           raise
   os.chmod('/dev/rfkill', 0o644)
   PY
   doas udevadm control --reload-rules
   doas udevadm trigger --action=change --subsystem-match=misc --sysname-match=rfkill
   doas udevadm settle
   ```

   As `jack`, verify both `test -r /dev/rfkill` and `test ! -w /dev/rfkill`
   succeed. Read access preserves Waybar's radio status after restart. Inspect
   `udevadm info --query=property --name=/dev/rfkill` and confirm its tags no
   longer include `uaccess`; confirm root retains write access. Once the staged
   controller runtime is installed, its `privacyctl status` check is available.
   Repeat the access check after a seat/session change and reboot. ACL changes
   do not revoke already-open file descriptors, so inspect existing rfkill
   handles before claiming exclusive controller access. This permissions step
   does not itself block, unblock, scan, or disconnect either radio. Root and
   separately granted doas privileges retain their existing authority. This
   host still has unrestricted wheel `nopass` doas access, so this step does
   not prevent a wheel user from regaining root authority.

   The `install` helper automates only this permission step with exact private
   backups and automatic rollback on failure. Copy the reviewed helper as
   `/usr/local/libexec/oldbook-radio/install` (root:root, `0750`) and the reviewed
   `72-privacy-rfkill.rules` beside it (`0644`); every ancestor must be root-owned
   and not writable by other users. Then run:

   ```sh
   doas /usr/local/libexec/oldbook-radio/install --prepare-permissions
   ```

   It prints its `0700` journal directory under
   `/var/lib/oldbook/radio-permissions`; `0600` JSON files contain the previous
   rule/device ACL and the pre/post Wi-Fi identity, without credentials. The
   helper requires an existing Wi-Fi association and refuses different existing
   rules. It verifies unchanged rfkill state, SSID/BSSID and IP addresses. It
   does not install the controller, start services, select networks, or block
   radios. Run Bluetooth-only preparation separately. A successfully prepared
   policy remains in place; preserve its journal for an explicit later recovery.

5. Add `radio-off` to the OpenRC `boot` runlevel and
   `privacyctl-supervisor` to the default runlevel. Its dependencies place the
   block before networking/wpa_supplicant and the supervisor after
   wpa_supplicant. Verify this graph and actual `supervise-daemon` startup in
   isolation before changing runlevels. Leave saved credentials root-only and automatic selection
   disabled until an explicit `privacyctl connect` call selects one permitted
   saved ID.

6. This host boots GRUB. In a root-only editor append exactly
   `rfkill.default_state=0` to `GRUB_CMDLINE_LINUX_DEFAULT` in
   `/etc/default/grub`, then regenerate `/boot/grub/grub.cfg` with the locally
   installed `grub-mkconfig`. Check `/proc/cmdline` and the running kernel’s
   rfkill parameter after reboot. This complements OpenRC; it does not prove
   that firmware or hardware emitted no RF before Linux takes control.

7. First verify blocked-state recovery after synthetic WPA control failures
   in the isolated owner fixture. Then validate on the local console:
   `doas privacyctl status --json`, `doas privacyctl off`, then
   `doas privacyctl scan`. Confirm Wi-Fi is blocked when the scan command
   exits. Only then test `doas privacyctl connect shmecklebucket`.
   Restore with `doas privacyctl off` before leaving the console.

8. Install the staged elogind hook at `/etc/elogind/system-sleep/95-radio-off`.
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
