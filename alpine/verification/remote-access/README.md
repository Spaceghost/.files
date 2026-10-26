# Remote access live verification — 2026-10-26

The live desktop runs the root-owned `oldbook-remote-access` observer from the
default OpenRC runlevel. Tailscale SSH remained enabled throughout deployment.
The current encrypted Wi-Fi was classified Friend-trusted through Incoming
Transmissions and the live state became `TAILNET + LAN`; OpenSSH started only
after validation and nftables admitted port 22 only from `wlan0`'s current IPv4
and IPv6 subnets. The status snapshot reported no degraded state and no
unexpected non-loopback listener.

[`incoming-transmissions.png`](incoming-transmissions.png) shows the separate
Remote access action exactly between Wi-Fi and Next art. It also captures the
fail-safe refusal to disable LAN passwords before a public key exists.
[`desktop-remote-watch.png`](desktop-remote-watch.png) shows the persistent,
obvious `REMOTE WATCH · TAILNET + LAN · FRIEND` desktop card.

Verification run:

- 104 focused/pinned remote-access and Wi-Fi tests passed.
- nftables check mode accepted the permanent policy.
- OpenSSH syntax and effective policy checks passed; root login and forwarding
  are disabled, while public-key and the currently selected LAN password
  authentication are enabled.
- The root config is mode `0600`, the sanitized status is `0644`, the service is
  started and boot-enabled, and OpenSSH is not itself boot-enabled.
- UI and observer transitions share a root-owned process lock; five concurrent
  live reconciliations serialized successfully. Re-running the installer also
  completed cleanly while OpenRC restarted the firewall's dependent services.
- Sway validation, JSON parsing, Python compilation, ShellCheck and a disposable
  HOME deployment passed.

The machine cannot prove an inbound Tailscale SSH connection to itself: a local
connection to its own tailnet address reaches ordinary OpenSSH routing and is
not a remote-tailnet test. An actual second-node connection remains the honest
way to populate and visually verify a live session row. The tailnet's external
SSH ACL/check-mode policy also remains administered outside this repository.
