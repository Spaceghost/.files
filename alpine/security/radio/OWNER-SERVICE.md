# Persistent radio owner service

This implementation is staged. The live WPA, DHCP and resolver owners have not
been replaced. Exact trusted SSIDs, controlled migration, live policy decisions
and reboot/suspend checks remain activation requirements.

## Commands and lifetime

`privacyctl supervise` runs an owner with a separate guardian. `connect PROFILE`
and `scan` submit root-only, bounded requests to `/run/privacyctl/owner.sock`.
They never fall back to the old direct-control code. `status [--json]` preserves
the existing read-only rfkill output and does not require the owner socket.

The owner starts blocked and clears stale session authorization before handling
requests. It checks the saved network's exact ID and SSID before unblocking,
then keeps one foreground DHCP client throughout successful renewals. A lease
is acknowledged only after native application and a second WPA identity check.
The successful CLI response commits the connection; later CLI exit does not
end it. A disconnected caller cancels an unfinished request.

`off`, failed association, lost WPA identity, lease failure or expiry first
invalidate authorization and block radios. Only then may client termination
and owned network cleanup run. Cleanup errors retain the handles and ownership
record; a replacement connection cannot bypass them. Idle checks reassert
blocking once per second. Healthy sessions have no arbitrary expiry timer.

## Cancellation barrier

Each scan/connect request carries the off-fence captured by the privileged CLI
before submission. Both ordinary and emergency off atomically change that
fence. A delayed older request cannot reactivate the radio afterward.

WPA send/receive waits and native lease application call cooperative checkpoints
at approximately 25 ms intervals. Those checkpoints ingest requests and lease
failures; they block on cancellation without recursively applying or removing
network state. Cleanup runs after those callbacks unwind, with cancellation
disabled and its own bounded deadline. Existing command/application deadlines
still bound each phase.

If owner IPC fails or off waits five seconds, the CLI publishes an emergency
fence and attempts blocking directly. Fence publication precedes a two-second
wait for the lock shared with unblock; it publishes again under that lock.
Failure still attempts both radio blocks and returns an error. A failed fence
write can never be reported as successful off.

## Process death and recovery

The guardian watches the owner through a pidfd and blocks before releasing its
lifetime lock. Owner parent-death SIGTERM requests shutdown if the guardian is
killed. During normal shutdown, the guardian blocks before asking the owner to
clean up. Separate process tests exercise both deaths and competing guardians.
The guardian resets inherited SIGCHLD handling before forking, preserving the
unreaped-child guarantee required by [Linux pidfd_open](https://man7.org/linux/man-pages/man2/pidfd_open.2.html).
Parent identity is checked after installing the
[parent-death signal](https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html).
These mechanisms do not guarantee silence if both processes are killed at once
or the kernel cannot execute the blocking operation.

Before native lease mutation, `lease-dirty` records its generation in the
root-private runtime directory. Successful owned cleanup removes it. A marker
surviving an owner crash prevents later connections; it is not automatically
deserialized into permission to delete addresses or resolver providers. Exact
orphan-state recovery remains part of the migration/recovery work. Do not
delete the marker merely to make a connection succeed.

## Private IPv6 configuration

`/etc/privacyctl/ipv6.json` must be root-owned mode 0600 or 0400 and explicitly
contain the selected profile. Missing settings are rejected before unblock.
The format below uses documentation addresses, never actual home settings:

```json
{"version":1,"profiles":{
  "shmecklebucket":{"addresses":["2001:db8:1::17/64"],"routers":["fe80::1"]},
  "iphone-hotspot":{"addresses":[],"routers":[]}
}}
```

The existing exact-SSID allowlist remains separate. Static IPv6 ownership does
not configure RA/SLAAC policy or remove legacy provisioning. Those decisions
must be made explicitly during the controlled migration.

See [LEASE-OWNER.md](LEASE-OWNER.md), [NETWORK-MIGRATION.md](NETWORK-MIGRATION.md)
and [owner-verification.json](owner-verification.json) for the separate component and native
integration scopes. No isolated fixture substitutes for a live radio, WPA,
firewall or boot acceptance check.

## Reproduce combined checks

From the checkout, use new output directories for each run:

```sh
doas python3 -B -m unittest discover -s alpine/security/radio/tests -v
python3 alpine/security/radio/tests/verify_radio_owner.py --output /tmp/radio-owner-proof
```

The combined fixture runs the production CLI, IPC, owner, DHCP client and native
lease applier in private namespaces. It substitutes a Unix-datagram WPA server
and virtual-interface radio state. Its 32-second lease allows native renewal;
the separate 16-second manager fixture still checks independent expiry.
During server silence, either authenticated deconfiguration or manager expiry
ends authorization; the evidence records which occurred first.

The verified run passed seven cases: same-client renewal, ordinary off, stale
request rejection, exact scan completion, home/hotspot IPv6 restoration, NAK
and server silence. Host-state comparisons matched and no test processes
survived. A separate seven-case fault fixture now runs the production guardian
with the same CLI, owner, DHCP and native applier. It verifies cancellation
during an unanswered WPA request and a paused native command, requesting-client
and DHCP-hook death, competing guardian refusal, and reciprocal guardian/owner
death. Blocking precedes native-command and DHCP teardown. Host-state checks
matched and no private processes survived. See
[fault-verification.json](fault-verification.json) for exact reasons, source
hashes and the preserved earlier reporting failure.

Owner death still retains an orphan marker and refuses replacement. The
[same-boot recovery design](ORPHAN-RECOVERY.md) is unimplemented. OpenRC startup,
physical radios and live network migration remain separate acceptance work.

The separate [packet-policy fixture](../firewall/radio-policy-verification.json)
now verifies DHCP renewal, exact IPv4 DNS rules, IPv6 neighbor discovery and
fresh DNS denial after daemon death. It preserves existing live rules and does
not replace the owner or OpenRC integration proof.

The veth interface exercises actual IPv6 duplicate-address detection. The
earlier dummy-interface applier checks bypassed DAD because Linux treats
NOARP interfaces specially ([kernel source](https://github.com/torvalds/linux/blob/v6.18/net/ipv6/addrconf.c#L406)).
Application has a four-second total cap while preserving the five-second hook
deadline. Delayed or failed DAD, cancellation and late acknowledgments still
reject the lease. This budget does not guarantee success on an overloaded host.
