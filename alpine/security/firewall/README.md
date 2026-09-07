# Application firewall

The Oldbook policy combines a permanent nftables table with OpenSnitch process
decisions. Installation alone does not start either service. The root controller
must finish local recovery and bootstrap application rules before activation.

The September 7 host trial was rolled back after additional broad Allow rules
appeared during validation. The daemon is stopped and startup is not enabled;
those interactive rules were preserved for review. See
[`activation-verification.json`](activation-verification.json) for actual results.

## Behavior

- Unsolicited incoming connections and forwarded traffic are denied for IPv4
  and IPv6. Loopback, reply traffic, DHCP and necessary ICMP/IPv6 neighbor
  discovery are allowed.
- New outgoing application connections enter NFQUEUE 0 without bypass. The
  daemon or GUI must explicitly permit an executable; no GUI means default-deny.
- The queue belongs to `inet oldbook`, independently of OpenSnitch's tables.
  The gate remains after a crash or graceful daemon shutdown. Established
  approved connections continue; this is a gate for new connections, not a
  promise to terminate every already-open socket when the daemon stops.
- Process inspection currently uses `/proc`. DNS mapping uses intercepted
  plaintext DNS replies; encrypted DNS does not provide equivalent domain
  visibility. eBPF byte accounting is not enabled in this package.

OpenSnitch's GUI cannot remove the independent gate using its pause control.
Change application rules in the GUI; edit the repository nftables policy for
system packet filtering. Changing the GUI default action to Allow makes unknown
applications allowed while that GUI is connected; retain Deny.

## Integration

Install the signed `opensnitch`, `opensnitch-ui` and `opensnitch-openrc` APKs after
installing the accompanying public signing key. Packages supply:

- `/etc/init.d/oldbook-firewall` and `/etc/init.d/opensnitchd`.
- `/etc/oldbook/firewall.nft` and root-only `/etc/opensnitchd/` policy.
- GUI defaults at `/etc/xdg/opensnitch/settings.conf`.

Enable and start `oldbook-firewall` before `opensnitchd` and before networking.
Do not also start a stock nftables service that flushes the complete ruleset.
The service's reload replaces only the Oldbook table in one atomic transaction.
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
    --output /tmp/oldbook-firewall-bootstrap
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
doas install -Dm755 alpine/security/firewall/activate /usr/local/sbin/oldbook-firewall-activate
firewall_trial=$(doas /usr/local/sbin/oldbook-firewall-activate start --timeout 600)
doas /usr/local/sbin/oldbook-firewall-activate status "$firewall_trial"
```

Before confirming, check fresh permitted connections and an unapproved program.
`verify-host --expect allow|deny --uid UID --output NEW-DIRECTORY` uses a temporary
veth peer to exercise actual host IPv4/IPv6 filtering without changing firewall
rules or contacting external servers. Run it with doas. Its outbound probe uses
a fresh executable path so an existing curl permission cannot mask the result.
Only a timeout with zero completed TCP connections counts as denial; local HTTP
controls must succeed. `probe-codex --output NEW-DIRECTORY`, run as the desktop
user, makes one minimal authenticated request using the saved CLI login.

After every check passes, `doas /usr/local/sbin/oldbook-firewall-activate confirm "$firewall_trial"`
enables both services in the **boot** runlevel, before networking. To abandon the
trial use `rollback` with that token. A confirmed token cannot later shut down
the firewall: ordinary post-confirmation recovery is the explicit procedure below.
Review newly created interactive rules before confirming; an Allow for all root
programs or all destination-port-443 traffic removes those application restrictions.

The desktop's `oldbook-firewall-ui` quietly starts the GUI only when both service
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
doas nft delete table inet oldbook
```

This explicitly removes packet/application protection. The ordinary daemon stop
does not do so. Restart `oldbook-firewall` and `opensnitchd` to restore protection.
An application firewall is not a sandbox for malicious root processes or a
proof of Wi-Fi/Bluetooth radio silence.
