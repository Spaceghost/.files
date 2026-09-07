# Bluetooth-only preparation

This policy soft-blocks Bluetooth when Linux/eudev observes a device addition or
state change. It leaves the deferred WLAN controller, saved networks, DHCP and
OpenRC services alone. It does not prove RF silence before Linux or a tested
reboot/suspend cycle.

## Current activation state

Preparation completed on this host on 2026-09-07. Independent read-only checks
at 14:13 UTC verified Bluetooth `soft=1`, `hard=0`, while WLAN remained
`soft=0`, `hard=0`. Association, IP addresses and normalized routes match the
private before/prepared snapshots. Installed helper/rule hashes, device
registrations, rule identity and private journal modes all match. Waybar's
status command reports Bluetooth blocked and WLAN enabled; no physical hover
or live unblock/rollback was injected. See
[bluetooth-verification.json](bluetooth-verification.json) for sanitized
evidence and the private recovery journal location.

The WLAN controller remains staged; its separate isolated tests are recorded
in [controller-verification.json](controller-verification.json). The commands
below are for rebuilding elsewhere or explicit recovery; preparation need not
be repeated on this verified host.

`71-privacy-bluetooth-off.rules` matches `rfkill` devices whose type is exactly
`bluetooth` and whose `soft` value is `0`, then writes `1`. Linux defines this as
software blocking and emits a change event when the state changes. The `soft=0`
condition avoids reapplying the rule to its own blocked-state event. These
semantics were checked against the [Linux 6.18 rfkill core](https://github.com/torvalds/linux/blob/v6.18/net/rfkill/core.c),
[sysfs ABI](https://github.com/torvalds/linux/blob/v6.18/Documentation/ABI/stable/sysfs-class-rfkill)
and [eudev 3.2.14 rule evaluator](https://github.com/eudev-project/eudev/blob/v3.2.14/src/udev/udev-rules.c).

## Install and verify

After review, copy `install-bluetooth` as root:root, mode `0750`, to
`/usr/local/libexec/oldbook-radio/install-bluetooth` and copy the reviewed rule
beside it as root:root, mode `0644`. It also requires the previously reviewed
permissions installer named `install` in that root-owned directory. Every
ancestor must be root-owned and unwritable by other users. Then run:

```sh
doas /usr/local/libexec/oldbook-radio/install-bluetooth --prepare
```

Preparation refuses any preexisting target rule and rechecks for Bluetooth
input, daemon, connection objects and audio before changing anything. It
requires an observable existing Wi-Fi association. It creates a private journal
under `/var/lib/oldbook/bluetooth-preparation`, installs only the Bluetooth rule,
reloads eudev and triggers only Bluetooth rfkill devices. It verifies their
soft blocks, unchanged hard blocks, and unchanged WLAN radios, SSID, BSSID, IP
addresses and routes. Route expiry countdowns are excluded from comparison.
The returned JSON includes an opaque token and journal path; retain them.

## Recovery

Preparation errors automatically attempt rollback. For explicit later rollback
within the same boot, use the exact token returned by preparation:

```sh
doas /usr/local/libexec/oldbook-radio/install-bluetooth --rollback TOKEN
```

Rollback first rejects changed device inventory. It removes only the installed
rule with its recorded inode/device, change timestamp and content hash, reloads
eudev, then restores the recorded Bluetooth soft states. Device type, name,
canonical sysfs path, registration inode/device and boot ID must still match.
Snapshots and restoration bind attributes to one held directory descriptor;
a reused rfkill index cannot retarget a write. A private nonblocking lock
serializes helper transactions. WLAN is never reconnected or changed. The rollback records its own
before/after state and is a no-op after successful recovery. A changed rule or
failed device check requires inspecting the private journal; it is preserved.
After a reboot, inspect current hardware identities before manual recovery.
Existing broad wheel/doas administration privileges remain unchanged.

## Reproduce isolated checks

```sh
python3 -m unittest discover -s alpine/security/radio/tests -v
python3 alpine/security/radio/verify-bluetooth-rule --output /tmp/bluetooth-rule-check
```

The parser check requires currently unblocked Bluetooth for its positive match.
It validates private mount/network namespaces before any mount operation, makes
sysfs read-only, and uses private rule directories and udev database. The exact
rule is parsed only for a nonmatching remove event. Add/change tests replace
the write with an inert environment marker; WLAN and remove events must reject
it. No live Bluetooth assignment or daemon reload occurs in this test.
