# Same-boot orphan lease recovery

**Status: journal and writer primitives implemented; recovery integration remains
staged.** This document specifies the remaining recovery work; it does not
authorize installation or activation. The current
`adapter.JournaledApplier` records only `lease-dirty`, and
`network.LeaseApplier` holds its `OwnedState` capability in process memory. A
marker left by an owner crash therefore prevents replacement; it does not yet
authorize cleanup or reconnect. Keep activation gated by
[INSTALL-PLAN.md](INSTALL-PLAN.md) and the ownership handoff in
[NETWORK-MIGRATION.md](NETWORK-MIGRATION.md).

## Implemented primitives

`privacyctl_runtime.journal` implements the bounded schema and durable file
store: `Journal(directory).read()`, `write(record)`, and `remove()`. It requires
an existing root-private directory and the caller's ownership locks. Its return
value is validated evidence, never permission to delete a network resource.

`privacyctl_runtime.writers` implements `current_context()`, `capture_writer()`
and `drain_writer()`. Capture borrows an already-open process pidfd while the
caller holds the execution gate closed. Drain validates the same boot and
namespace view, opens its own pidfd before reading process identity, and never
signals by numeric PID. Journal and writer validators share the same schema.

The two modules have 57 focused tests using disposable files and mocked process
operations; see [orphan-primitives-verification.json](orphan-primitives-verification.json).
They are not connected to `NativeNetwork`, `DHCPManager` or owner startup yet.
These tests do not establish the deployed-kernel descendant-death proof or
working orphan cleanup. Existing runtime modules and activation state are
unchanged. The APIs below describe the future coordinator over these primitives.

## Decision and scope

Use a root-private write-ahead journal, a random per-link ifalias cookie, and authenticated records of the actual native/DHCP namespace-init processes captured before their execution gates open. This is a practical same-boot recovery design for the current exclusive radio owner. A separate cgroup mechanism is not required for the first implementation if the PID-namespace proof and gate coverage below are implemented and fault-tested. Reboot remains a fallback for unresolved identity or teardown failures.

The trust boundary is unprivileged interference and crashes of trusted privileged components. Privacyctl reserves its protocol-196 resources, generation-specific resolver provider, and temporary link alias while active. Other legitimate privileged managers must honor the existing explicit ownership handoff. A hostile root process can forge the journal or copy a cookie and already has authority to alter or delete host networking; that is not an obstacle to implementing ordinary crash recovery. Unexpected privileged changes are detected as conflicts where possible and never authorize broader deletion.

## Kernel proof checked

Linux v6.12 `zap_pid_ns_processes()` prevents further PID allocation, kills remaining namespace processes, waits for children including externally parented cases, then waits until only init's own PID accounting remains. Its explicit invariant is that reaping namespace init implies all processes in that namespace are gone. Processes cannot move themselves into an ancestor PID namespace; detached sessions remain contained. [kernel/pid_namespace.c](https://github.com/torvalds/linux/blob/v6.12/kernel/pid_namespace.c#L160)

`exit_notify()` calls parent/child-reaper handling, including that namespace teardown, before assigning `EXIT_ZOMBIE`. Consequently the single-threaded namespace-init exit state is published after descendant teardown. [kernel/exit.c](https://github.com/torvalds/linux/blob/v6.12/kernel/exit.c#L668)

`pidfd_poll()` reports process completion when its task is gone, or when exit state is set and the thread group is empty. Use a process pidfd with flags 0, not PIDFD_THREAD. Combined with the ordering above, readiness of the authenticated original init pidfd is a usable writer-death barrier. [fs/pidfs.c](https://github.com/torvalds/linux/blob/v6.12/fs/pidfs.c#L168)

These observations support the proposed inference: confirmed disappearance/reuse of an originally verified host PID belonging to namespace init also means that old init passed teardown. Missing namespace metadata alone is weaker and must not be treated as completion. Validate this proof on the supported deployed kernel with the fault cases below; v6.12 is the pinned source baseline for this design; it is not evidence of a completed test on the deployed kernel.

Ifalias is a per-device management string, and writing it requires CAP_NET_ADMIN in the device network namespace. An ordinary unprivileged process cannot set the host device cookie. [ifalias ABI](https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-class-net), [net-sysfs implementation](https://github.com/torvalds/linux/blob/master/net/core/net-sysfs.c)

## Proposed internal APIs

These are trusted Python interfaces, not caller-selected IPC paths or executables:

```python
Journal.begin(generation, boot_id, observer_pidns, target_netns,
              ifindex, previous_alias, cookie)
Journal.prepare_operation(operation, before_owned, possible_after_owned,
                          writer_identity)
Journal.finish_operation(verified_owned, writer_dead=True)
Journal.prepare_alias_restore()
Journal.finish_clean()

NativeNetwork(..., journal=journal)  # persist inside _run before gate release
DHCPManager(..., journal=journal)    # persist init identity before ready ACK

Recovery(runtime=DEFAULT_RUNTIME, state=FIXED_STATE).recover(deadline=...)
# Returns CLEAN or raises RecoveryError; failure retains journal and radio block.
```

Keep `LeaseApplier._require_current()` unchanged for live capabilities. Recovery validates the disk record and constructs a separate internal recovery capability; arbitrary `OwnedState(**json)` is never a deletion authorization. Owner startup invokes recovery while holding its lifetime locks, before opening readiness or beginning a new generation. Recovery never automatically reconnects or adopts the expired lease. Fresh connect/scan must capture the post-recovery fence.

## Journal schema and atomicity

One bounded fixed-path record in a persistent root-owned mode-0700 directory, root-owned mode-0600 single-link regular file. Store version, generation, monotonically increasing operation sequence, phase, boot ID, observer PID-namespace identity, target network-namespace identity, fixed interface/ifindex, random cookie, exact previous alias bytes, conservative old/proposed resource sets, possible provider contents, and the active native/DHCP writer slots. The per-boot namespace identities prevent reading the same numeric PID through an unrelated container's /proc view.

A writer identity contains kind, original host PID, start-time ticks, PID-namespace dev/inode, and proof captured at registration that the process was namespace PID 1. Keep launcher identity for diagnostics/reaping, but launcher exit is not the descendant-death proof. No executable path or numeric PID kill is interpreted directly from JSON. Decode exact schema with duplicate-key/depth/size limits; reject unsafe ancestors, symlink/hardlink/nonregular files, wrong owner/mode, invalid versions or contradictory identities.

For every native mutation, retain the complete old state plus the proposed target before releasing its gate. Address/route candidates contain exact deletion selectors. DNS candidates contain both the previous and proposed complete generation-provider contents. Failed/uncertain operations retain both possibilities; a verified outcome may narrow them. A deletion intent keeps the object until absence is verified. Journal writes use O_EXCL temp files, file fsync, atomic rename, directory fsync; a failed write never opens the gate. Recovery's own mutation commands obey the same protocol so recovery can itself crash and resume.

Do not clear a writer slot before authentic init death is proved. Normal serialization bounds this to one native command plus one persistent DHCP init. Journal an empty resource set before the initial resolver probe: command ownership exists before `OwnedState` does. Missing writer identity is safe only for a specifically recorded pre-gate phase whose owner-only gate writer was never released; arbitrary missing slots in a mutating phase are corruption.

## Link-cookie lifecycle

1. While blocked and exclusive, capture boot/netns/ifindex plus the exact prior alias bytes, generate a fresh token such as `privacyctl:<32hex>`, and durably record `alias-intent`. Reject an unexplained existing privacyctl cookie.
2. Set the alias through the same authenticated native command gate and verify it. Persist `alias-installed` before any lease resource can be added. The cookie remains unchanged through renewals of that generation.
3. Before recovery deletes a candidate, verify boot/netns/ifindex/cookie still match. If an interface was destroyed/recreated, its absent/different cookie blocks deletion even if name or index was reused. Never replace a mismatching cookie merely to make recovery continue.
4. After all owned resources and resolver effects are absent and all writers are dead, durably enter `alias-restore-intent`, then restore the captured alias only if the current alias is the cookie. Verify the restored bytes, commit clean, and remove the journal. If recovery crashed after restoration, an already-restored alias is accepted only in this final phase, with no further lease-resource deletes. Earlier phases with missing cookie remain conflicts.

Preserving/restoring the previous alias is an owned metadata operation, not an instruction to reset all interface properties. Bytes must round-trip exactly within the kernel alias bound; do not normalize arbitrary preexisting alias text.

Practical execution detail: operations must retain the captured interface identity through the native gate. Current `ip ... dev <name>` resolves a name later; a rename/name-reuse window can redirect it. Prefer a small constrained netlink mutation backend using the recorded ifindex, with cookie checks immediately around mutation, or explicitly preserve the exclusive no-rename/no-other-configurator contract throughout each operation. An alias is an identity cookie, not an atomic compare-and-delete primitive. Concurrent deliberate CAP_NET_ADMIN link replacement cannot be made impossible by a JSON record; detectable changes abort and the activation handoff must exclude competing configurators. Same-boot index reuse present before recovery is directly covered by the cookie check.

## Register writers before mutation can happen

NativeNetwork already creates a namespace init held behind a pipe gate. After readiness, open the actual init pidfd, verify host PID/start/PID namespace/NSpid ends in 1 and both launcher/init are live, then fsync the operation intent and writer record. Recheck authorization and only then write the gate frame. A crash before that point closes the sole gate writer, so the fixed bootstrap cannot execute a host-mutating command. A crash after it leaves the exact writer identity and authorized mutation scope on disk.

Apply the same registration boundary to DHCPManager's ready ACK before PID 1 execs udhcpc. Persisting only short-lived `ip`/resolver commands misses the persistent DHCP owner and its hooks. Fixed native commands and subscribers must remain in these descendant PID namespaces; setsid does not escape. A nested descendant namespace is still part of the ancestor init's teardown responsibility.

Recovery acquires the existing guardian, owner, and DHCP ownership locks in that order, before examining a journal for cleanup. Startup must expose lock acquisition separately from IPC readiness and DHCP child launch. After guardian exclusivity, invalidate the request fence and verify radio blocks before any teardown; retain all acquired ownership locks through recovery. Never wait for a long teardown while recursively holding RadioLock from an unblock checkpoint. When any ownership lock is busy, return a bounded failure rather than recovering alongside its holder. A surviving guardian must finish its own owner supervision before another recovery invocation acquires its lock. The implementation must keep this order consistent across startup, shutdown, and recovery, including any future journal lock.

For each pending writer, with boot and observer namespace already validated:

- Call `pidfd_open(record.pid, 0)` first. ESRCH confirmed against the same /proc view means the old init is absent. EMFILE/permission/read errors are not absence and block recovery.
- Read start time and PID-namespace identity through one opened /proc process directory; recheck pidfd readiness around the reads. If the recorded start time is demonstrably different, the old PID has been reused: do not signal the new process; mark the old init gone. Read races that cannot establish this cleanly are retried or refused.
- If start/namespace/NSpid identity matches and the pidfd is already readable, it is done. If matched and still live, send SIGKILL using only that pidfd and wait for process readiness under the recovery deadline. Because identity was checked after opening the pidfd, numeric reuse cannot redirect the signal.
- Matching start with contradictory namespace, missing metadata without a completion proof, or a timeout keeps the journal and refuses kernel/DNS cleanup. Do not classify every changed field as safe PID reuse.
- Persist the writer slot as complete only after this proof. Never waitpid an unrelated replacement; a recovery process may not be the old init's parent, so authenticated pidfd completion is the required barrier.

This removes the need for a general cgroup implementation here. A cgroup remains a reasonable later alternative if the project wants one stable generation-wide process registry; it is not needed merely because the original pidfds died with the owner.

## Recover exact resources and partial DNS

After all old writers are proved dead, turn the union journal into a recovery capability. For each candidate, absence is success; an exact expected object may be removed; a conflicting object with the same deletion key causes refusal. Preserve unrelated protocols/addresses/routes and the existing primary-IPv4/secondary-prefix guard. Never sweep all protocol-196 objects. Before finishing, unexplained reserved-protocol objects are diagnostic conflicts, not extra deletion candidates.

For a generation provider, allow only the recorded complete old/new contents. Unexpected or malformed contents are a conflict unless an explicitly proven atomic-provider-write implementation narrows how partial states can arise. Delete only the exact derived provider key. A provider can already be absent while generated resolver output still contains its old DNS; the current `remove_dns()` only detects this and cannot always repair it.

Add a fixed-path bounded native resolver regeneration operation under the real openresolv lock/host-PID bridge and validated libc-only policy. Rebuild from the current complete validated provider set, preserving newer unrelated providers. Do not delete nameserver lines by value or restore an old resolver snapshot. Unmanaged/symlinked replacement outputs or unreviewed subscriber policy remain failures. Recovering a torn generated output requires an established managed-destination authority; malformed output alone must not authorize arbitrary overwrite.

Only after verification, writer drain, and alias restoration may the durable marker be cleared. Failed block, journal I/O, native drain, exact-state verification, or resolver rebuild retains ownership evidence and prevents replacement. Recovery remains cancellable/bounded at waits but cannot report clean on partial completion.

## Next bounded implementation and fault tests

The next implementation must connect the journal store and writer helpers to gated writer registration, the ifalias lifecycle, and the recovery core with synthetic backends. Review these together because a persisted resource set without authenticated writer death is insufficient. Keep activation disabled until the following fault cases also pass in isolated PID, mount, and network namespaces. The implementation does not include UI, unrelated networking migration, or a general cgroup manager.

1. Kill owner before/after alias intent, alias mutation, alias verification, each resource intent/mutation, DNS update, writer-slot completion, and final alias restoration. Re-run recovery twice; preserve unrelated state and prior alias.
2. Keep a matching old init alive with detached and nested-namespace descendants, kill owner and guardian, then recover from a new process. Verify pidfd-based kill and completed namespace teardown precede every resource deletion.
3. Test genuine old-init absence and a recorded PID replaced by an unrelated live process: recovery never signals the replacement. Test matching-start/contradictory-namespace and metadata-read races: no cleanup without a completion proof.
4. Hold namespace init in teardown by controlled parent-namespace tracing/child reaping (or another isolated deterministic harness); ensure recovery times out blocked until init completion, then succeeds. Do not synthesize a host unkillable process.
5. Recreate/rename the link and reuse name/index with unrelated resources, without copying the private cookie: refuse deletion. Change alias during a recovery checkpoint: stop. Verify alias-restore-intent resumes after a crash without requiring the already-restored cookie.
6. Fail fsync/rename before every execution gate; no corresponding native mutation may occur. Truncate/duplicate/oversize/symlink/hardlink/wrong-owner the record; remain blocked. An empty OwnedState with a pending writer still requires drain.
7. Crash renewal in mixed old/new address/route/DNS states; exact union candidates clean up while unrelated resources survive. Cover primary IPv4 with an unrelated secondary.
8. Exercise absent provider plus stale generated output, partial provider/output write, unrelated provider update during recovery, and unmanaged destination. Verify scoped rebuild and conflict handling.
9. Recover with a different boot ID: never signal old PIDs or delete current kernel addresses/routes; use only the conservative resolver/record completion fallback.
10. Measure journal and writer-record fsync cost against the existing 4-second apply / 5-second hook budget. Current native apply already performs many guarded commands. Read-only probes may eventually use a boot-local writer registry because their identities need not survive reboot, but do not add that optimization until the simple durable implementation is measured and its gate proof remains complete.

Ordinary same-boot crashes should recover through this protocol once it is implemented and verified. Reboot remains a conservative fallback when identity or teardown cannot be proved; the current marker-only implementation still refuses same-boot orphan cleanup.
