# Application firewall

The MBP Intel policy combines a permanent nftables table with OpenSnitch process
decisions. Installation alone does not start either service. The root controller
must finish local recovery and bootstrap application rules before activation.

The September 7 interactive activation is running and both services are enabled
in the boot runlevel. All 28 existing rule files and popup defaults were
preserved. New non-443 connections produced a real Qt popup and Deny verdict;
IPv4/IPv6 incoming checks, fresh authenticated Codex and curl checks passed.
The desktop was locked, so an unlocked human click remains untested. See
[`interactive-verification.json`](interactive-verification.json). The earlier
rolled-back trial remains recorded in
[`activation-verification.json`](activation-verification.json).

## Behavior

- Unsolicited incoming connections and forwarded traffic are denied for IPv4
  and IPv6. Loopback, reply traffic, DHCP and necessary ICMP/IPv6 neighbor
  discovery are allowed.
- New outgoing application connections enter NFQUEUE 0 without bypass. Matching
  rules decide access; unmatched connections prompt in the GUI. Without a GUI,
  unmatched connections receive the daemon's default Deny.
- The queue belongs to `inet mbp-intel`, independently of OpenSnitch's tables.
  The gate remains after a crash or graceful daemon shutdown. Established
  output flows remain allowed by this table. OpenSnitch's separate DNS input
  queue can still drop UDP DNS replies after daemon death; the gate does not
  terminate every already-open socket.
- Process inspection currently uses `/proc`. DNS mapping uses intercepted
  plaintext DNS replies; encrypted DNS does not provide equivalent domain
  visibility. eBPF byte accounting is not enabled in this package.

OpenSnitch's GUI cannot remove the independent gate using its pause control.
Change application rules in the GUI; edit the repository nftables policy for
system packet filtering. Changing the GUI default action to Allow makes unknown
applications allowed while that GUI is connected; retain Deny.

## Interactive decisions

Normal operation asks Allow or Deny for connections without a matching rule,
then remembers the selected scope and duration. Existing permissions remain in
effect: a port-only allowance covers every application using that port, and a
user-only allowance covers that user's programs. Restarting the daemon does not
require deleting these choices. [Upstream popup guide](https://github.com/evilsocket/opensnitch/wiki/Pop-ups-dialogs).

Current defaults are Deny after 20 seconds, popups enabled, executable target,
and 12-hour duration. In version 1.8.0, duration index `6` means `12h`; `0` means
Once, `7` means until restart, and `8` means Forever. Keep the existing defaults
unless changing them is requested. Future application-specific decisions can
combine the executable with UserID and optional destination conditions.

Upstream's optional learning workflow uses default Allow and temporary rules;
ordinary interactive prompting does not require enabling it. Do not select
Ignore rules to force relearning: that preference can delete temporary rules.
[Upstream getting-started guide](https://github.com/evilsocket/opensnitch/wiki/Getting-started).

## Radio packet verification

The radio networking checks are recorded in
[radio-policy-verification.json](radio-policy-verification.json). Six isolated
cases passed with the installed BusyBox, nftables and OpenSnitch binaries:

- Raw DHCP acquisition bypassed inet output; actual same-client unicast renewal
  used the existing UDP 68→67 exception and received an accepted acknowledgment.
- IPv4 UDP/TCP DNS was denied without a queue consumer or an application rule.
  One exact rule allowed the selected executable, UID and resolver, including
  processes in a nested PID namespace; different values were denied.
- Real IPv6 duplicate-address detection and hoplimit-255 neighbor solicitation
  passed. The hoplimit-254 control reached the filter and was blocked.
- Killing the private daemon removed its queue consumer and denied fresh DNS.

These tests use synthetic servers and controlled rules. They preserve the
installed broad root/443 grants, which still affect live prompts. They do not
activate the staged radio owner or prove a trusted physical association.

Re-run from the repository with a new evidence directory:

```sh
python3 -B alpine/security/firewall/verify-radio-policy.py --output /tmp/radio-policy-proof
```

The fixture uses private PID, mount and network namespaces and an explicitly
empty eBPF module directory. OpenSnitch 1.8.0 starts its DNS BPF listener even
with process monitoring set to `proc`; the empty module path prevents loading
before any tracing can attach. The proof records this boundary and retains all
four failed fixture runs with their diagnostics.

## Package and session integration

Install the signed `opensnitch`, `opensnitch-ui` and `opensnitch-openrc` APKs after
installing the accompanying public signing key. Packages supply:

- `/etc/init.d/mbp-intel-firewall` and `/etc/init.d/opensnitchd`.
- `/etc/mbp-intel/firewall.nft` and root-only `/etc/opensnitchd/` policy.
- GUI defaults at `/etc/xdg/opensnitch/settings.conf`.

Enable and start `mbp-intel-firewall` before `opensnitchd` and before networking.
Do not also start a stock nftables service that flushes the complete ruleset.
The service's reload replaces only the MBP Intel table in one atomic transaction.
The service's stop deliberately retains its rules.

Run the GUI as Jack after creating `$XDG_RUNTIME_DIR/opensnitch` with mode 0700:

```sh
opensnitch-ui --socket "unix://$XDG_RUNTIME_DIR/opensnitch/osui.sock"
```

The supplied daemon socket targets UID 1000. Adjust it to the restored user's UID
if that changes. Keep rules and daemon configuration owned by root. Establish
explicit rules for approved browsers, DNS clients, package tools, time sync and
Codex before relying on unattended use. Allowing `/bin/busybox` alone permits all
its applets: combine its executable rule with narrowly chosen ports/destinations.

## Explicit bootstrap staging

`bootstrap-rules` creates a new private staging directory, without contacting the
network or changing installed rules, packages or services. Supply every approved
executable explicitly. For example, after selecting and inspecting the executable
and current resolver addresses:

```sh
alpine/security/firewall/bootstrap-rules \
    --uid 1000 --executable /opt/codex/0.153.4/cli/bin/codex \
    --resolver 75.75.75.75 --resolver 75.75.76.76 \
    --output /tmp/mbp-intel-firewall-bootstrap
```

Repeat `--executable` for another explicitly approved path and `--resolver` for
another resolver. Paths must be absolute and normalized; symbolic links in
executables or staging paths are rejected. The output must not already exist,
and its parent must exist. Invalid inputs are rejected before staging starts.

Each executable gets an AND rule for its exact case-sensitive path, numeric UID,
supplemental MD5, TCP/TCP6 and destination port 443. Separate rules permit
TCP/UDP DNS on port 53 to each exact resolver IP with the same executable and UID
conditions. No processes are discovered or automatically approved. Interpreters,
BusyBox applets and root processes gain no general exception. The helper does
not generate NTP or other application policies.

The private `rules/` directory contains only installable rule JSON, mode 0600;
`manifest.json` is outside it and records rule SHA-256 values, executable SHA-256
and MD5 values, owners, modes and sizes. Output directories are mode 0700. MD5 is
the algorithm registered by OpenSnitch 1.8.0's checksum loader. SHA-256 is audit
evidence, not a supported rule operand. OpenSnitch can match a missing checksum
or ignore checksum matching when disabled, so these are **not cryptographic
fail-closed executable identity rules**. Retain `Rules.EnableChecksums=true`.

A trusted installer must compare the staging manifest with its explicit approved
path list and the current executable files, then install only `rules/*.json` as
root:root mode 0600. Never copy `manifest.json` into OpenSnitch's rules directory
or treat a user-writable staging manifest as authorization. Existing Codex
processes can be executing a backed-up binary path after an upgrade; the
installer should inspect and explicitly approve that path as well as the current
installation when preserving those sessions. The generator never harvests
`/proc` or broadens rules to parent processes.

Stage bootstrap rules before daemon startup. OpenSnitch 1.8.0's live watcher
handles file writes and removals but does not reload a rule replaced by atomic
rename. Do not assume a rename of staged files updates the running policy.

## Reversible first activation

Review and install bootstrap rules, then install the reviewed activation helper
in a root-owned directory. It refuses an existing gate, daemon, queue or service
runlevel link. Its detached watchdog must complete a handshake before any packet
rules load. A timed-out, failed or explicitly rolled-back trial removes only its
gate, daemon and new boot links; it never flushes unrelated tables or conntrack.

```sh
doas install -Dm755 alpine/security/firewall/activate /usr/local/sbin/mbp-intel-firewall-activate
firewall_trial=$(doas /usr/local/sbin/mbp-intel-firewall-activate start --timeout 600)
doas /usr/local/sbin/mbp-intel-firewall-activate status "$firewall_trial"
```

Before confirming, check fresh permitted connections and an unapproved program.
`verify-host --expect allow|deny --uid UID --output NEW-DIRECTORY` uses a temporary
veth peer to exercise actual host IPv4/IPv6 filtering without changing firewall
rules or contacting external servers. Run it with doas. Its outbound probe uses
a fresh executable path so an existing curl permission cannot mask the result.
Only a timeout with zero completed TCP connections counts as denial; local HTTP
controls must succeed. `probe-codex --output NEW-DIRECTORY`, run as the desktop
user, makes one minimal authenticated request using the saved CLI login.

With a retained port-443 exception, use `--port 18443` to exercise a connection
outside it. For a real interactive check, add `--timeout 30 --expect-output either`
while retaining `--expect deny` for incoming traffic. Observe the real GUI popup
and resulting rule separately: `either` records the actual outgoing verdict and
does not by itself prove prompting. A user's Allow is valid test behavior.
Screen locking can obscure an otherwise mapped popup; do not bypass the lock.
Remove only the unique canary's rule after the check; keep every existing rule.
The verification record includes the exact canary name, cleanup events and the
private root-owned backup under `/var/lib/mbp_intel/firewall-backups/`.

After every check passes, `doas /usr/local/sbin/mbp-intel-firewall-activate confirm "$firewall_trial"`
enables both services in the **boot** runlevel, before networking. To abandon the
trial use `rollback` with that token. A confirmed token cannot later shut down
the firewall: ordinary post-confirmation recovery is the explicit procedure below.
Review newly created interactive rules before confirming; an Allow for all root
programs or all destination-port-443 traffic removes those application restrictions.

The desktop's `mbp-intel-firewall-ui` quietly starts the GUI only when both service
links are enabled. It uses the private runtime socket and prevents duplicates
across session reloads. A GUI already started manually on `/tmp/osui.sock` must
be restarted with the documented runtime address before daemon integration.

Bootstrap `created` and `updated` fields use the fixed policy revision date in
`POLICY_TIMESTAMP`. This preserves deterministic staging and avoids OpenSnitch's
repeated RFC3339 warnings when exporting rules to the GUI.

## Verification and recovery

```sh
doas python3 alpine/security/firewall/test-netns.py --daemon /usr/bin/opensnitchd
python3 -m unittest discover -s alpine/security/firewall -p 'test_bootstrap_rules.py' -v
```

The test immediately enters a new network namespace and creates a second one
for its HTTP server. It checks IPv4 and IPv6 allow/deny, different executables,
rule changes, no-daemon startup, and SIGTERM/SIGKILL. It never installs rules in
the host namespace. Generated bootstrap rules are also exercised unchanged on
TCP port 443: an exact executable and UID are allowed, while another UID,
executable, port or populated checksum is denied. Restoring the correct checksum
restores access. That endpoint serves plain HTTP; this verifies packet policy,
not TLS. Unit tests check the precise resolver and protocol restrictions, audit
hashes, private output modes, deterministic staging and unsafe-input rejection.
GUI interaction and boot ordering require separate live tests.
Retained bootstrap results and source/binary hashes are in
[`bootstrap-verification.json`](bootstrap-verification.json).

For deliberate emergency recovery at a local TTY, after reviewing the impact:

```sh
doas rc-service opensnitchd stop
doas nft delete table inet mbp-intel
```

This explicitly removes packet/application protection. The ordinary daemon stop
does not do so. Restart `mbp-intel-firewall` and `opensnitchd` to restore protection.
An application firewall is not a sandbox for malicious root processes or a
proof of Wi-Fi/Bluetooth radio silence.
