# Same-boot orphan lease recovery

**Status: same-boot recovery is integrated in staged source; nine isolated
native cases passed with injected journal delay.** Owner startup now takes the guardian, owner and DHCP lifetime
locks before recovering the durable lease journal, and opens IPC readiness only
after recovery succeeds. `NativeNetwork`, `LeaseApplier` and `DHCPManager` share
one `RecoveryJournal`. Recovery verifies writer death and link identity before
removing exact recorded lease resources and restoring the previous alias. It
does not reconnect. No live service or radio ownership has been changed by this
integration. Keep activation gated by [INSTALL-PLAN.md](INSTALL-PLAN.md) and
[NETWORK-MIGRATION.md](NETWORK-MIGRATION.md).

## Implementation and evidence

`privacyctl_runtime.journal` implements the bounded schema and durable file
store: `Journal(directory).read()`, `write(record)`, `remove()` and
`confirm_absent()`. It requires an existing root-private directory and the
caller's ownership locks. Decoded data is validated evidence, never permission
to delete a network resource. The narrowly scoped absence confirmation fsyncs
the directory after a known clean-removal attempt; it never deletes a file.

`privacyctl_runtime.writers` implements `current_context()`, `capture_writer()`
and `drain_writer()`. Capture borrows an already-open process pidfd while the
caller holds the execution gate closed. Drain validates the same boot and
namespace view, opens its own pidfd before reading process identity, and never
signals by numeric PID. `link.read_link()` reads raw alias bytes through rtnetlink.
The recovery coordinator checks those identities and issues an ephemeral permit
for `LeaseApplier.remove_recovered()` only after the old writers are gone.

The historical [orphan-primitives-verification.json](orphan-primitives-verification.json)
records 57 focused tests at 2026-09-07T17:59:51.139608+00:00 against its listed
source hashes, before runtime integration. Its historical limitations remain
part of that record. The current source-stable non-root discovery passed 270
tests and skipped 95 root-only cases using synthetic backends, mocked process
operations and disposable private files/sockets. Its command and source hashes
are recorded in [checkpoint-verification.json](checkpoint-verification.json);
this discovery is not root or native recovery evidence.

Native run 07 passed nine cases in 118.3246 seconds with 50 ms injected per
journal write. The run covered cancellation, guardian/owner death, exact orphan
cleanup, prior-alias restoration, fresh explicit connect/off and repeated clean
startup. All recorded host comparisons matched, no fixture namespace members
survived, and source hashes were unchanged. See
[orphan-integration-verification.json](orphan-integration-verification.json).
Runs 01–06 remain preserved failures: 03/04 exposed the earlier four-second
apply cap, 06 hit the unchanged 0.75-second native command cap under load, and
02 retains an unexplained pre-existing DHCP-process inventory delta.

This is private PID/mount/network namespace evidence with a tmpfs journal and
artificial delay, not integrated real-persistent-disk timing. WPA and physical
radio operations are guarded fixture substitutes. An init was alive when its
owner was killed, but completed before replacement startup; the run does not
prove draining a surviving writer from a new observer. That proof, controlled
namespace-teardown timing, different-boot completion and actual OpenRC/live
activation acceptance remain separate.

## Decision and scope

Use a root-private write-ahead journal, a random per-link ifalias cookie, and authenticated records of the actual native/DHCP namespace-init processes captured before their execution gates open. This is a practical same-boot recovery design for the current exclusive radio owner. A separate cgroup mechanism is not required for the first implementation if the PID-namespace proof and gate coverage below are implemented and fault-tested. Reboot terminates old kernel writers, but persistent DNS intent still needs explicit retirement. The separate staged v2 path and its validation limits are documented in [DIFFERENT-BOOT-RECOVERY.md](DIFFERENT-BOOT-RECOVERY.md).

The trust boundary is unprivileged interference and crashes of trusted privileged components. Privacyctl reserves its protocol-196 resources, generation-specific resolver provider, and temporary link alias while active. Other legitimate privileged managers must honor the existing explicit ownership handoff. A hostile root process can forge the journal or copy a cookie and already has authority to alter or delete host networking; that is not an obstacle to implementing ordinary crash recovery. Unexpected privileged changes are detected as conflicts where possible and never authorize broader deletion.

## Kernel proof checked

Linux v6.12 `zap_pid_ns_processes()` prevents further PID allocation, kills remaining namespace processes, waits for children including externally parented cases, then waits until only init's own PID accounting remains. Its explicit invariant is that reaping namespace init implies all processes in that namespace are gone. Processes cannot move themselves into an ancestor PID namespace; detached sessions remain contained. [kernel/pid_namespace.c](https://github.com/torvalds/linux/blob/v6.12/kernel/pid_namespace.c#L160)

`exit_notify()` calls parent/child-reaper handling, including that namespace teardown, before assigning `EXIT_ZOMBIE`. Consequently the single-threaded namespace-init exit state is published after descendant teardown. [kernel/exit.c](https://github.com/torvalds/linux/blob/v6.12/kernel/exit.c#L668)

`pidfd_poll()` reports process completion when its task is gone, or when exit state is set and the thread group is empty. Use a process pidfd with flags 0, not PIDFD_THREAD. Combined with the ordering above, readiness of the authenticated original init pidfd is a usable writer-death barrier. [fs/pidfs.c](https://github.com/torvalds/linux/blob/v6.12/fs/pidfs.c#L168)

These observations support the proposed inference: confirmed disappearance/reuse of an originally verified host PID belonging to namespace init also means that old init passed teardown. Missing namespace metadata alone is weaker and must not be treated as completion. Validate this proof on the supported deployed kernel with the fault cases below; v6.12 is the pinned source baseline for this design; it is not evidence of a completed test on the deployed kernel.

Ifalias is a per-device management string, and writing it requires CAP_NET_ADMIN in the device network namespace. An ordinary unprivileged process cannot set the host device cookie. [ifalias ABI](https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-class-net), [net-sysfs implementation](https://github.com/torvalds/linux/blob/master/net/core/net-sysfs.c)

## Integrated internal APIs

These are trusted Python interfaces, not caller-selected IPC paths or executables:

```python
store = Journal('/var/lib/privacyctl')  # fixed production lease.json path
journal = RecoveryJournal(store, backend, interface='wlan0', marker=dirty_marker)
journal.begin(generation, deadline=deadline, check=checkpoint)
journal.record_owned(owned)            # exact trusted OwnedState, including unions
journal.writer_started(kind, pid, pidfd, operation)  # durable before gate release
journal.writer_finished(kind)         # caller has proved the captured init dead
journal.check_link(deadline=deadline, check=checkpoint)
journal.finish(deadline=deadline, check=checkpoint)
journal.recover(deadline=deadline, check=checkpoint)  # 'clean' or an exception

NativeNetwork(..., journal=journal)
DHCPManager(..., journal=journal)
```

`Server.acquire()` separates owner locking from `Server.listen()` readiness.
`DHCPManager.acquire()` takes its lifetime lock without starting a client;
`stop()` retains an explicitly acquired lock, and terminal `close()` stops before
releasing it. Production starts under guardian exclusivity, acquires owner then
DHCP ownership, calls `NativeAdapter.prepare_recovery()`, binds the same journal
to DHCP, starts the owner, and finally listens. Recovery first invalidates the
request fence and verifies radio blocking, with a 16-second startup recovery deadline.

`LeaseApplier._require_current()` still requires the live object capability.
Recovery validates the disk record and issues a separate internal permit;
arbitrary `OwnedState(**json)` is never deletion authorization. The wrapper
retains failed cleanup and uses recovery when journal completion is uncertain,
instead of starting another live mutation from stale memory. Failed DHCP stop
prevents lease removal. No method adopts the expired lease or reconnects; fresh
connect/scan must capture the post-recovery fence.

## Journal schema and atomicity

One bounded fixed-path record in a persistent root-owned mode-0700 directory, root-owned mode-0600 single-link regular file. Store version, generation, monotonically increasing operation sequence, phase, boot ID, observer PID-namespace identity, target network-namespace identity, fixed interface/ifindex, random cookie, exact previous alias bytes, conservative old/proposed resource sets, possible provider contents, and the active native/DHCP writer slots. The per-boot namespace identities prevent reading the same numeric PID through an unrelated container's /proc view.

Each native/DHCP writer slot contains the original host PID, start-time ticks, PID-namespace dev/inode, namespace PID 1 proof and a bounded diagnostic operation tag. Keep launcher identity for diagnostics/reaping, but launcher exit is not the descendant-death proof. No executable path or numeric PID kill is interpreted directly from JSON. Decode exact schema with duplicate-key/depth/size limits; reject unsafe ancestors, symlink/hardlink/nonregular files, wrong owner/mode, invalid versions or contradictory identities.

For every native mutation, retain the complete old state plus the proposed target before releasing its gate. Address/route candidates contain exact deletion selectors. DNS candidates contain both the previous and proposed complete generation-provider contents. Failed/uncertain operations retain both possibilities; a verified outcome may narrow them. A deletion intent keeps the object until absence is verified. Journal writes use O_EXCL temp files, file fsync, atomic rename, directory fsync; a failed write never opens the gate. Recovery's own mutation commands obey the same protocol so recovery can itself crash and resume.

Do not clear a writer slot before authentic init death is proved. Normal serialization bounds this to one native command plus one persistent DHCP init. Journal an empty resource set before the initial resolver probe: command ownership exists before `OwnedState` does. Missing writer identity is safe only for a specifically recorded pre-gate phase whose owner-only gate writer was never released; arbitrary missing slots in a mutating phase are corruption.

## Link-cookie lifecycle

1. While blocked and exclusive, capture boot/netns/ifindex plus the exact prior alias bytes, generate a fresh token such as `privacyctl:<32hex>`, and durably record `alias-intent`. Reject an unexplained existing privacyctl cookie.
2. Set the alias through the same authenticated native command gate and verify it. Persist `active` before any lease resource can be added. The cookie remains unchanged through renewals of that generation.
3. Before recovery deletes a candidate, verify boot/netns/ifindex/cookie still match. If an interface was destroyed/recreated, its absent/different cookie blocks deletion even if name or index was reused. Never replace a mismatching cookie merely to make recovery continue.
4. After all owned resources and resolver effects are absent and all writers are dead, durably enter `alias-restore-intent`, then restore the captured alias only if the current alias is the cookie. Verify the restored bytes, commit clean, and remove the journal. If recovery crashed after restoration, an already-restored alias is accepted only in this final phase, with no further lease-resource deletes. The active phase requires the cookie; initial alias-intent may still have the prior alias if installation never completed.

Preserving/restoring the previous alias is an owned metadata operation, not an instruction to reset all interface properties. Bytes must round-trip exactly within the kernel alias bound; do not normalize arbitrary preexisting alias text.

Practical execution detail: operations must retain the captured interface identity through the native gate. Current `ip ... dev <name>` resolves a name later; a rename/name-reuse window can redirect it. Prefer a small constrained netlink mutation backend using the recorded ifindex, with cookie checks immediately around mutation, or explicitly preserve the exclusive no-rename/no-other-configurator contract throughout each operation. An alias is an identity cookie, not an atomic compare-and-delete primitive. Concurrent deliberate CAP_NET_ADMIN link replacement cannot be made impossible by a JSON record; detectable changes abort and the activation handoff must exclude competing configurators. Same-boot index reuse present before recovery is directly covered by the cookie check.

## Register writers before mutation can happen

NativeNetwork already creates a namespace init held behind a pipe gate. After readiness, open the actual init pidfd, verify host PID/start/PID namespace/NSpid ends in 1 and both launcher/init are live, then fsync the operation intent and writer record. Recheck authorization and only then write the gate frame. A crash before that point closes the sole gate writer, so the fixed bootstrap cannot execute a host-mutating command. A crash after it leaves the exact writer identity and authorized mutation scope on disk.

Apply the same registration boundary to DHCPManager's ready ACK before PID 1 execs udhcpc. Persisting only short-lived `ip`/resolver commands misses the persistent DHCP owner and its hooks. Fixed native commands and subscribers must remain in these descendant PID namespaces; setsid does not escape. A nested descendant namespace is still part of the ancestor init's teardown responsibility.

Recovery acquires the existing guardian, owner, and DHCP ownership locks in that order, before examining a journal for cleanup. Startup exposes lock acquisition separately from IPC readiness and DHCP child launch. After guardian exclusivity, invalidate the request fence and verify radio blocks before any teardown; retain all acquired ownership locks through recovery. Never wait for a long teardown while recursively holding RadioLock from an unblock checkpoint. When any ownership lock is busy, return a bounded failure rather than recovering alongside its holder. A surviving guardian must finish its own owner supervision before another recovery invocation acquires its lock. The implementation must keep this order consistent across startup, shutdown, and recovery, including any future journal lock.

For each pending writer, with boot and observer namespace already validated:

- Call `pidfd_open(record.pid, 0)` first. ESRCH confirmed against the same /proc view means the old init is absent. EMFILE/permission/read errors are not absence and block recovery.
- Read start time and PID-namespace identity through one opened /proc process directory; recheck pidfd readiness around the reads. If the recorded start time is demonstrably different, the old PID has been reused: do not signal the new process; mark the old init gone. Read races that cannot establish this cleanly are retried or refused.
- If start/namespace/NSpid identity matches and the pidfd is already readable, it is done. If matched and still live, send SIGKILL using only that pidfd and wait for process readiness under the recovery deadline. Because identity was checked after opening the pidfd, numeric reuse cannot redirect the signal.
- Matching start with contradictory namespace, missing metadata without a completion proof, or a timeout keeps the journal and refuses kernel/DNS cleanup. Do not classify every changed field as safe PID reuse.
- Persist the writer slot as complete only after this proof. Never waitpid an unrelated replacement; a recovery process may not be the old init's parent, so authenticated pidfd completion is the required barrier.

This removes the need for a general cgroup implementation here. A cgroup remains a reasonable later alternative if the project wants one stable generation-wide process registry; it is not needed merely because the original pidfds died with the owner.

## Recover exact resources and partial DNS

After all old writers are proved dead, turn the union journal into a recovery capability. For each candidate, absence is success; an exact expected object may be removed; a conflicting object with the same deletion key causes refusal. Preserve unrelated protocols/addresses/routes and the existing primary-IPv4/secondary-prefix guard. Never sweep all protocol-196 objects. Before finishing, unexplained reserved-protocol objects are diagnostic conflicts, not extra deletion candidates.

For a generation provider, allow only the recorded complete old/new contents. Unexpected or malformed contents are a conflict unless an explicitly proven atomic-provider-write implementation narrows how partial states can arise. Delete only the exact derived provider key. A provider can already be absent while generated resolver output still contains its old DNS. Recovery regenerates that output from current providers before and after exact provider deletion.

`NativeNetwork.regenerate_dns()` uses fixed `resolvconf -u` under the real openresolv lock/host-PID bridge and validated libc-only policy. It validates the complete current provider set and preserves unrelated providers; it never deletes nameserver lines by value or restores an old resolver snapshot. An intact managed-output signature is required before repairing a torn payload. Missing signatures, unmanaged/symlinked replacements, malformed provider contents and unreviewed subscriber policy remain failures. Malformed output alone never authorizes takeover.

Only after verification, writer drain, and alias restoration may the durable marker be cleared. Failed block, journal I/O, native drain, exact-state verification, or resolver rebuild retains ownership evidence and prevents replacement. Recovery remains cancellable/bounded at waits but cannot report clean on partial completion.

## Current staged timing limits

Application has a ten-second deadline and resource removal twelve seconds.
Both hook client and manager allow twelve seconds for acknowledgment; launcher
and manager readiness remain five seconds. Normal alias finish remains three
seconds, while startup recovery and the wrapper's uncertain-cleanup recovery
use sixteen seconds. The guardian allows twenty-five seconds after requesting
owner shutdown, followed by its three-second killed-owner death wait. Staged
OpenRC uses `retry='TERM/35/KILL/5'` to leave additional guardian cleanup margin;
that service-manager schedule still requires isolated OpenRC acceptance.

Lease expiry and the twenty-second acquisition deadline are unchanged. Deadlines
do not make synchronous fsync preemptible, and longer limits do not authorize
expired leases or report partial cleanup as clean. The selected fixture's six
address/route selectors (K=6) do not establish completion for the largest
accepted configuration (K=22). In run 07, maximum measured apply was 9.0522
seconds, live removal 6.6911, recovered removal 7.8271 and startup recovery
8.1318. These maxima describe that tmpfs fixture with 50 ms injected delay;
full integrated real-persistent-disk timing remains pending.

## Remaining native acceptance and fault tests

The journal store, gated writer registration, ifalias lifecycle, exact resource recovery and startup locks are connected and independently reviewed. Synthetic tests cover uncertain writes, conservative resource sets, refused identities and repeated cleanup. Keep activation disabled until native fault evidence establishes the applicable cases below in isolated PID, mount and network namespaces. The implementation does not include UI, unrelated networking migration, or a general cgroup manager. This list is an acceptance checklist, not a claim that every case has passed.

1. Kill owner before/after alias intent, alias mutation, alias verification, each resource intent/mutation, DNS update, writer-slot completion, and final alias restoration. Re-run recovery twice; preserve unrelated state and prior alias.
2. Keep a matching old init alive with detached and nested-namespace descendants, kill owner and guardian, then recover from a new process. Verify pidfd-based kill and completed namespace teardown precede every resource deletion.
3. Test genuine old-init absence and a recorded PID replaced by an unrelated live process: recovery never signals the replacement. Test matching-start/contradictory-namespace and metadata-read races: no cleanup without a completion proof.
4. Hold namespace init in teardown by controlled parent-namespace tracing/child reaping (or another isolated deterministic harness); ensure recovery times out blocked until init completion, then succeeds. Do not synthesize a host unkillable process.
5. Recreate/rename the link and reuse name/index with unrelated resources, without copying the private cookie: refuse deletion. Change alias during a recovery checkpoint: stop. Verify alias-restore-intent resumes after a crash without requiring the already-restored cookie.
6. Fail fsync/rename before every execution gate; no corresponding native mutation may occur. Truncate/duplicate/oversize/symlink/hardlink/wrong-owner the record; remain blocked. An empty OwnedState with a pending writer still requires drain.
7. Crash renewal in mixed old/new address/route/DNS states; exact union candidates clean up while unrelated resources survive. Cover primary IPv4 with an unrelated secondary.
8. Exercise absent provider plus stale generated output, partial provider/output write, unrelated provider update during recovery, and unmanaged destination. Verify scoped rebuild and conflict handling.
9. A different boot ID now selects the separate staged v2 DNS-only retirement path. Synthetic tests cover durable rollover, current-boot helper records and exact DNS cleanup; native resolver and genuine reboot acceptance remain separate. Old PIDs, kernel resources and aliases never grant authority in this mode. See [DIFFERENT-BOOT-RECOVERY.md](DIFFERENT-BOOT-RECOVERY.md).
10. Root-owned disk measurements found journal fsync latency of 38 ms median, 50 ms p95 and 70 ms maximum. Native runs 03 and 04 preserved actual failures of the earlier four-second apply cap; run 07 passed the nine-case fixture with 50 ms injected journal delay. The current staged limits are ten seconds for apply and twelve for removal and hook acknowledgment. Individual-write measurements do not establish complete real-persistent-disk integration timing. The dual-stack fixture has K=6 exact address/route selectors; the maximum accepted K=22 has no completion guarantee. Read-only probe optimizations must preserve writer registration and the gate proof.

Same-boot recovery has passed the scoped nine-case native fixture and remains staged pending the remaining acceptance checks. Malformed records, unknown markers, changed identities and unresolved teardown retain evidence and refuse replacement. Reboot can end old kernel writers, but does not make the persistent journal safe to discard: different-boot completion uses the separately tested staged v2 path and still needs native/reboot acceptance.
