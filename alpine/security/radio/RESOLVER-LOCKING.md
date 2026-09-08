# Resolver locks and PID namespaces

The native lease runner keeps one command and its descendants in a private PID
namespace. It records both launcher and namespace-init pidfds before releasing
the command. Parent death, timeout and interruption can therefore remove the
whole process tree, including children that create new sessions.

Stock openresolv 3.17.4 is not compatible with sharing its state across those
namespaces. Its lock directory contains the shell's `$$`; contenders use
`kill -0` to decide whether that PID is alive. A nested writer can mistake a
live outer writer for a stale lock. A killed nested writer can leave PID 1,
which a later namespace mistakes for its own live init. A private `/proc`
mount does not change `kill` semantics, and private lock directories would
remove serialization with other providers.

`tests/verify_resolver_pid_lock.py` reproduces both failures with synthetic
provider data and private network, PID and mount namespaces. The original
failure evidence must remain separate from any fixed-backend acceptance proof.
No live resolver file was changed by this reproduction.

## Compatibility bridge

The selected fix is an explicit, reproducibly packaged upstream-source patch,
not runtime editing. Ordinary host callers retain their normal native lock.
The namespace runner passes its recorded outer-visible init PID and an
inherited directory descriptor for the original `/proc` view. An opted-in
resolver writes that visible PID into the same native lock and checks other
owners in that original process view.

The resolver must validate the supplied view and identity before mutating state.
It must reject missing or invalid bridge context instead of falling back to
namespace PID 1. Native read-only helper invocations by subscribers must remain
usable. A capability probe lets `NativeNetwork` refuse the stock implementation
before lease application changes any addresses.

The ABI is `resolvconf --host-pid-lock-version` returning `1`, with
`OPENRESOLV_HOST_PID` and `OPENRESOLV_HOST_PROC_FD` supplied by the runner's
pidfd handshake. The patch verifies numeric bounds, procfs type and the current
shell PID through that original view. It performs identity validation before
mutating command paths; read-only subscriber children retain their native use.
Both environment variables are generated internally, with no request override.

This process namespace controls lifetime; it is not a general security sandbox.
The inherited original process view is deliberately available for lock checks.
The reviewed resolver configuration is limited to libc output without service
restart hooks. The live machine's existing configuration and hooks are not
automatically replaced by installing the capability patch.

## Acceptance requirements

- A live ordinary provider's lock remains intact when a nested writer contends.
- An ordinary caller recognizes a live nested writer's recorded host PID.
- Both kinds of caller recover a killed nested writer's stale lock.
- Invalid bridge descriptors or identities cause no provider or resolver change.
- Namespace containment, output limits and descriptor cleanup still pass.
- Real IPv4/IPv6 renewal and cleanup finish within the existing application
  deadline, preserving unrelated providers and state.

The six private bridge acceptance groups and seven native applier cases passed;
the stock-script negative control reproduced both original failures. Source
hashes, host-state comparisons and process cleanup are recorded separately in
[network-verification.json](network-verification.json). The reproducible APK
recipe is [../../packages/openresolv](../../packages/openresolv).

To rerun against an extracted patched script without installing it, use new
output directories from the checkout:

```sh
python3 alpine/security/radio/tests/verify_resolver_bridge.py --resolvconf /tmp/openresolv-root/usr/sbin/resolvconf --output /tmp/resolver-bridge-proof
python3 alpine/security/radio/tests/verify_network_applier.py --resolvconf /tmp/openresolv-root/usr/sbin/resolvconf --output /tmp/native-lease-proof
```

For the negative control, pass the archived stock 3.17.4-r0 script to
`tests/verify_resolver_pid_lock.py --resolvconf ... --output ...`.

The radio owner service and controlled resolver takeover remain separate
integration work. Do not enable the legacy one-shot controller or treat a
single-writer test as evidence of resolver serialization.
