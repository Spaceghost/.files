# Application firewall

The Oldbook policy combines a permanent nftables table with OpenSnitch process
decisions. Installation alone does not start either service. The root controller
must finish local recovery and bootstrap application rules before activation.

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

## Verification and recovery

```sh
doas python3 alpine/security/firewall/test-netns.py --daemon /usr/bin/opensnitchd
```

The test immediately enters a new network namespace and creates a second one
for its HTTP server. It checks IPv4 and IPv6 allow/deny, different executables,
rule changes, no-daemon startup, and SIGTERM/SIGKILL. It never installs rules in
the host namespace. GUI interaction and boot ordering require separate live tests.

For deliberate emergency recovery at a local TTY, after reviewing the impact:

```sh
doas rc-service opensnitchd stop
doas nft delete table inet oldbook
```

This explicitly removes packet/application protection. The ordinary daemon stop
does not do so. Restart `oldbook-firewall` and `opensnitchd` to restore protection.
An application firewall is not a sandbox for malicious root processes or a
proof of Wi-Fi/Bluetooth radio silence.
