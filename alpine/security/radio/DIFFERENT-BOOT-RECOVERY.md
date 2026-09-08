# Different-boot DNS retirement

Status: implemented in staged source, with synthetic and disposable-file tests.
No real reboot, live radio/controller activation, native DNS retirement or timing
acceptance is claimed here. Same-boot native fixture evidence predates this
extension and does not prove the new path.

Startup keeps the established guardian, owner and DHCP ownership order, blocks
radios and invalidates the request fence before recovery, and listens only after
recovery succeeds. Missing journal plus missing marker retains the existing
clean path. An unexplained marker still refuses startup.

## Identity and durable transition

Version 1 remains the ordinary lease format. A different current kernel boot ID
proves that its recorded kernel objects and namespace-init writers no longer
survive under the trusted kernel, root-owned storage and consistent `/proc` view
assumptions. Namespace mismatch alone does not prove reboot. A same-boot changed
observer or target network namespace remains a refusal. Suspend/resume does not
qualify, and boot IDs are never supplied by DHCP or IPC clients.

`Journal.rollover_boot(context)` requires an existing loaded, unchanged disk
instance and a different effective boot. It atomically increments the sequence,
retains the original generation, boot/namespace identity, interface, ifindex,
cookie and prior alias as provenance, and preserves exact DNS provider intent.
It discards extinct address/route candidates and old writer slots. The ordinary
`write` API cannot perform this transition or change effective context. A failed
rename/fsync retains old or new evidence for reload; it never removes the old
journal before replacement.

Version 2 has the same original fields plus exactly `recovery_context`, holding
current `boot_id`, `observer_pidns` and `target_netns`. Its only phases are
`reboot-dns` and `reboot-clean`. Address/route lists and the DHCP slot must be
empty. A native writer may exist only in `reboot-dns`; `reboot-clean` requires
all resources and slots empty. Current and original boot IDs must differ.
Normal v2 writes cannot change context or reopen a completed retirement. A
second reboot uses the same explicit rollover transition to discard extinct
recovery-helper records while retaining unresolved DNS intent.

## DNS-only authority

The new coordinator mode never queries the old link, installs a cookie,
restores the prior alias, constructs recovered kernel ownership or deletes an
address or route. Existing interfaces may have reused names/indexes, different
aliases or unrelated current configuration. A later normal generation still
must establish its own link identity and reject unexplained cookies.

`DNSRecoveryPermit` is an ephemeral capability issued only after the current
writer barrier succeeds. It is distinct from the kernel `RecoveryPermit`.
`NativeNetwork` checks actual immutable command arguments before creating a
helper and again after durable writer registration, immediately before opening
the execution gate. DNS retirement allows only its fixed backend's resolvconf
capability probe, `-u`, and `-f -d` for the exact recorded provider. It rejects
stdin, `ip`, provider creation, arbitrary provider keys and other options.
Diagnostic operation tags do not confer authority. Ordinary v1 command checks
retain the existing link/cookie fence.

Every new resolver helper has its actual init identity recorded against the
current recovery context before the gate opens. A same-boot retry drains that
writer through the existing pidfd-first proof. No old-boot PID is opened or
signalled. Registration uncertainty and local retained handles keep their
existing completion rules; failures retain evidence and prevent readiness.

## Persistent resolver cleanup

When no provider intent exists, no resolver action is necessary. Otherwise the
backend validates fixed libc-only policy and the intact managed output
signature, then prepares only missing fixed state/keys directories under
validated root-owned ancestors. Existing symlinks, legacy `interfaces` layout,
non-directories or unsafe ownership/modes refuse. This handles a fresh `/run`
with persistent generated output. It never uses `resolvconf -I`, which clears
unrelated provider state.

Before regeneration, an existing generation provider must exactly match a
recorded complete content possibility; absence is allowed. Regeneration uses
current provider inputs under the existing openresolv host-PID lock bridge.
The backend rechecks and removes only the exact provider key, proves absence,
regenerates again, and verifies that lease-only nameservers are gone while
shared nameservers belonging to surviving providers remain. It never deletes
resolver lines by value or restores an old output snapshot. Malformed provider
nameservers, unmanaged output, missing signatures and unreviewed policy/hooks
remain conflicts. Unrelated providers are retained.

Only successful DNS verification and completed writers allow durable empty
resources, then `reboot-clean`, matching-marker clearance and exact journal
unlink plus directory fsync. Known unlink/fsync uncertainty uses the existing
absence-confirmation retry; unexpected disappearance still refuses. Completed
retirement requires no old alias proof.

## Validation and remaining proof

The focused run passed 144 tests covering the new path together with existing
journal, same-boot coordinator, native gate mocks, startup ordering and DHCP
journal regressions. Another 60 pure network/writer/link regressions passed.
These selected suites intentionally exclude native namespace/process fixtures.
New coverage includes root-owned temporary journal rollover and fsync faults,
context mismatch, second reboot, current-helper drain ordering/failure, exact
command authorization on both gate boundaries, provider conflicts and shared
DNS, missing transient state, partial delete/retry, clean-phase/unlink
uncertainty, and temporary ownership locks before IPC readiness.

A synthetic boot-ID change cannot establish actual reboot behavior. Native
acceptance must still verify persistent journal/output with a fresh `/run`,
current-boot helper crash/drain, managed resolver repair and deadline pressure
in an isolated fixture, then distinguish that evidence from a genuine reboot.
No timeout was increased: startup recovery retains its sixteen-second deadline.
Synchronous fsync remains non-preemptible, and this new path has no real-disk
completion guarantee.
