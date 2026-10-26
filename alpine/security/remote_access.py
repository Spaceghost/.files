"""Policy and presentation primitives for Oldbook remote access.

This module deliberately has no privileged side effects.  The root controller
supplies a machine boundary, while tests and report renderers use the same
policy without needing a live firewall or daemon.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import struct


VALID_MODES = ("off", "tailnet", "lan")
LAN_TRUST = ("home", "friend", "trusted")
PUBLIC_KEY_TYPES = {
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
}
INTERFACE = re.compile(r"[A-Za-z0-9_.:-]{1,15}\Z")
ACCOUNT = re.compile(r"[a-z_][a-z0-9_-]{0,31}\Z")
RETENTION_SECONDS = 24 * 60 * 60
DISPLAY_LIMIT = 12


def _lan_reason(context):
    trust = str(context.get("trust", "untrusted")).lower()
    if trust not in LAN_TRUST:
        return "The current network is untrusted; LAN access is closed."
    if str(context.get("security", "")).lower() in ("", "open", "none"):
        return "Open or unidentified Wi-Fi cannot authorize LAN access."
    if not context.get("password") and int(context.get("keys", 0) or 0) < 1:
        return "LAN access has no usable authentication method."
    if not INTERFACE.fullmatch(str(context.get("interface", ""))):
        return "The active network interface is not safe to authorize."
    try:
        networks = [ipaddress.ip_network(value, strict=False)
                    for value in context.get("subnets", [])]
    except ValueError:
        return "The active LAN subnet could not be verified."
    if not networks or any(network.prefixlen == 0 for network in networks):
        return "The active LAN subnet could not be verified."
    return ""


def apply_mode(machine, desired, context):
    """Apply a desired mode with the LAN-open operation strictly last."""
    if desired not in VALID_MODES:
        raise ValueError(f"unknown remote-access mode: {desired}")

    # This is both cleanup and a transaction fence: no later failure can leave
    # a previous network's allowance behind.
    machine.remove_lan()
    if desired == "off":
        machine.stop_sshd()
        machine.set_tailnet(False)
        return {"desired": desired, "effective": "off", "reason": ""}

    reason = _lan_reason(context) if desired == "lan" else ""
    if desired == "tailnet" or reason:
        machine.stop_sshd()
        machine.set_tailnet(True)
        return {"desired": desired, "effective": "tailnet", "reason": reason}

    machine.set_tailnet(True)
    machine.validate_sshd()
    machine.start_sshd()
    machine.add_lan(context["interface"], context["subnets"])
    return {"desired": desired, "effective": "lan", "reason": ""}


def firewall_fragment(interface, subnets):
    """Build only narrow SSH accepts; callers install them atomically."""
    if not INTERFACE.fullmatch(str(interface)):
        raise ValueError("invalid interface")
    rows = []
    for value in subnets:
        network = ipaddress.ip_network(value, strict=False)
        if network.prefixlen == 0:
            raise ValueError("a default route is not a LAN boundary")
        family = "ip" if network.version == 4 else "ip6"
        rows.append(f'        iifname "{interface}" {family} saddr {network} '
                    'tcp dport 22 accept comment "Oldbook trusted LAN SSH"')
    if not rows:
        raise ValueError("at least one LAN subnet is required")
    return "\n".join(rows) + "\n"


def validate_public_key(value):
    """Return an OpenSSH public key's type and payload, never its comment."""
    value = str(value or "").strip()
    if "PRIVATE KEY" in value or "\n" in value or "\r" in value:
        raise ValueError("Paste one OpenSSH public key, never a private key.")
    fields = value.split()
    if len(fields) < 2:
        raise ValueError("Paste one OpenSSH public key.")
    key_type, payload = fields[:2]
    if key_type not in PUBLIC_KEY_TYPES:
        raise ValueError("The first field must be a supported public key type.")
    try:
        raw = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("The public key payload is not valid base64.") from None
    if len(raw) < 8 or len(raw) > 16384:
        raise ValueError("The public key payload has an invalid size.")
    size = struct.unpack(">I", raw[:4])[0]
    try:
        embedded = raw[4:4 + size].decode("ascii")
    except UnicodeDecodeError:
        embedded = ""
    if embedded != key_type:
        raise ValueError("The public key type does not match its payload.")
    return key_type, payload


def sshd_config(account, password, authorized_keys):
    """Generate the complete restrictive OpenSSH policy owned by this feature."""
    if not ACCOUNT.fullmatch(str(account)):
        raise ValueError("invalid local account")
    authorized_keys = Path(authorized_keys)
    if not authorized_keys.is_absolute():
        raise ValueError("authorized keys path must be absolute")
    answer = "yes" if password else "no"
    return "\n".join([
        "# Generated by oldbook-remote-access; edit through Incoming Transmissions.",
        "PermitRootLogin no",
        "PubkeyAuthentication yes",
        f"PasswordAuthentication {answer}",
        f"KbdInteractiveAuthentication {answer}",
        "PermitEmptyPasswords no",
        "AllowAgentForwarding no",
        "AllowTcpForwarding no",
        "AllowStreamLocalForwarding no",
        "GatewayPorts no",
        "X11Forwarding no",
        "PermitTunnel no",
        f"AllowUsers {account}",
        "",
        f"Match User {account}",
        f"    AuthorizedKeysFile .ssh/authorized_keys {authorized_keys}",
        "",
    ])


def _network_identity(network):
    identifier = str(network.get("uuid", "")).strip()
    if not identifier or len(identifier) > 128:
        raise ValueError("The saved Wi-Fi network has no stable identity.")
    return identifier


def network_trust(network, registry):
    """Return trust only when profile, security, and access point all match."""
    try:
        entry = (registry or {}).get(_network_identity(network)) or {}
    except ValueError:
        return "untrusted"
    trust = entry.get("trust", "untrusted")
    if trust not in ("home", "friend", "untrusted"):
        return "untrusted"
    if trust == "untrusted":
        return trust
    if entry.get("ssid") != network.get("ssid"):
        return "untrusted"
    if str(entry.get("security", "")).lower() != str(network.get("security", "")).lower():
        return "untrusted"
    bssid = str(network.get("bssid", "")).lower()
    approved = {str(value).lower() for value in entry.get("bssids", [])}
    return trust if bssid and bssid in approved else "untrusted"


def remember_network_trust(registry, network, trust):
    """Return a new authoritative trust registry with this AP recorded."""
    if trust not in ("home", "friend", "untrusted"):
        raise ValueError("Trust must be Home, Friend-trusted, or Untrusted.")
    identifier = _network_identity(network)
    security = str(network.get("security", "")).strip()
    if trust != "untrusted" and security.lower() in ("", "open", "none"):
        raise ValueError("Open networks cannot be trusted for LAN access.")
    updated = {key: dict(value) for key, value in (registry or {}).items()}
    prior = updated.get(identifier, {})
    bssids = {str(value).lower() for value in prior.get("bssids", []) if value}
    bssid = str(network.get("bssid", "")).lower()
    if trust != "untrusted":
        if not bssid:
            raise ValueError("The current access point identity is unavailable.")
        bssids.add(bssid)
    updated[identifier] = {
        "trust": trust,
        "ssid": str(network.get("ssid", ""))[:128],
        "security": security[:64],
        "bssids": sorted(bssids) if trust != "untrusted" else [],
    }
    return updated


def safe_process_chain(values):
    """Reduce observed executable names to a bounded, non-sensitive chain."""
    result = []
    for raw in values or []:
        token = str(raw).replace("\x00", " ").split(None, 1)[0]
        name = Path(token).name.rstrip(":")
        name = "".join(character for character in name
                       if character.isalnum() or character in "._+-@")[:24]
        if name and (not result or result[-1] != name):
            result.append(name)
        if len(result) == 4:
            break
    return result


def _tailnet_address(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address in ipaddress.ip_network("100.64.0.0/10") or \
        address in ipaddress.ip_network("fd7a:115c:a1e0::/48")


def sessions_from_processes(processes, peers, authentication, key_labels):
    """Turn root-read process observations into sanitized live SSH sessions."""
    groups = {}
    for process in processes:
        connection = str(process.get("connection", "")).split()
        if len(connection) != 4:
            continue
        identifier = "ssh-" + hashlib.sha256(
            " ".join(connection).encode()).hexdigest()[:20]
        group = groups.setdefault(identifier, {"connection": connection, "rows": []})
        group["rows"].append(process)

    sessions = []
    for identifier, group in groups.items():
        connection = group["connection"]
        source_ip, source_port = connection[0], connection[1]
        rows = sorted(group["rows"], key=lambda row: (float(row.get("started", 0)),
                                                       int(row.get("pid", 0))))
        peer = (peers or {}).get(source_ip)
        tailnet = peer is not None or _tailnet_address(source_ip)
        if tailnet:
            device = _safe_text((peer or {}).get("device") or source_ip, 32)
            identity = _safe_text((peer or {}).get("user") or "unknown tailnet peer", 48)
            source = f"tailnet · {device}"
            auth = "Tailscale identity"
        else:
            identity = _safe_text(source_ip, 48)
            source = f"LAN · {identity}"
            event = (authentication or {}).get((source_ip, source_port), {})
            method = event.get("method")
            if method == "key":
                fingerprint = str(event.get("fingerprint", "unknown"))
                shown = fingerprint if len(fingerprint) <= 24 else fingerprint[:21] + "…"
                label = (key_labels or {}).get(fingerprint, "unlabelled key")
                auth = f"key · {_safe_text(label, 32)} · {shown}"
            elif method in ("password", "keyboard-interactive"):
                auth = "LAN password"
            else:
                auth = "unknown"
        sessions.append({
            "id": identifier, "live": True,
            "started": min(float(row.get("started", 0)) for row in rows),
            "account": _safe_text(rows[0].get("account") or "?", 16),
            "identity": identity, "source": source, "auth": auth,
            "processes": safe_process_chain(row.get("comm", "") for row in rows
                                             if row.get("comm") not in
                                             ("sshd", "sshd-session", "tailscaled")),
        })
    sessions.sort(key=lambda row: -row["started"])
    return sessions


def summarize_tailnet(document):
    """Sanitize `tailscale status --json` for fleet and identity displays."""
    users = {str(key): value for key, value in (document.get("User") or {}).items()}
    peers = []
    address_map = {}
    for peer in (document.get("Peer") or {}).values():
        user = users.get(str(peer.get("UserID")), {})
        row = {
            "device": _safe_text(peer.get("HostName") or peer.get("DNSName") or "unknown", 48),
            "user": _safe_text(user.get("LoginName") or "unknown", 64),
            "addresses": [_safe_text(value, 48) for value in peer.get("TailscaleIPs", [])],
            "online": bool(peer.get("Online")), "os": _safe_text(peer.get("OS"), 20),
            "last_seen": _safe_text(peer.get("LastSeen"), 40),
            "exit_node": bool(peer.get("ExitNodeOption")),
            "routes": [_safe_text(value, 48) for value in peer.get("PrimaryRoutes", [])],
        }
        peers.append(row)
        for address in row["addresses"]:
            address_map[address] = {"device": row["device"], "user": row["user"]}
    peers.sort(key=lambda row: (not row["online"], row["device"].lower()))
    return {"online": sum(1 for row in peers if row["online"]),
            "total": len(peers), "peers": peers, "addresses": address_map}


def classify_hatches(listeners, snapshot, serve=False, funnel=False):
    """Separate local/known listeners from unexplained remotely bound sockets."""
    local, known, unexpected = [], [], []
    for original in listeners:
        row = dict(original)
        address = str(row.get("address", ""))
        try:
            loopback = ipaddress.ip_address(address.strip("[]")).is_loopback
        except ValueError:
            loopback = address in ("localhost", "::1")
        if loopback:
            local.append(row)
        elif row.get("process") == "tailscaled" or (
                int(row.get("port", 0)) == 22 and snapshot.get("mode") == "lan"
                and (snapshot.get("observed") or {}).get("lan")):
            known.append(row)
        else:
            unexpected.append(row)
    return {"local": local, "known": known, "unexpected": unexpected,
            "serve": bool(serve), "funnel": bool(funnel)}


def merge_sessions(existing, observed, now):
    """Merge a live observation into the rolling 24-hour session ledger."""
    records = {str(row["id"]): dict(row) for row in existing if row.get("id")}
    seen = set()
    for incoming in observed:
        identifier = str(incoming.get("id", ""))
        if not identifier:
            continue
        seen.add(identifier)
        prior = records.get(identifier, {})
        current = dict(prior)
        current.update(incoming)
        if incoming.get("auth") in (None, "", "unknown") and prior.get("auth") not in (
                None, "", "unknown"):
            current["auth"] = prior["auth"]
        if prior.get("started") is not None:
            current["started"] = prior["started"]
        current["live"] = True
        current.pop("ended", None)
        current["processes"] = safe_process_chain(current.get("processes", []))
        records[identifier] = current

    for identifier, record in records.items():
        if record.get("live") and identifier not in seen:
            record["live"] = False
            record["ended"] = now

    retained = [record for record in records.values()
                if record.get("live") or now - float(record.get("ended", 0)) < RETENTION_SECONDS]
    retained.sort(key=lambda row: (
        0 if row.get("live") else 1,
        -float(row.get("started") if row.get("live") else row.get("ended", 0))))
    return retained


def _safe_text(value, limit=48):
    value = str(value or "").replace("$", "＄")
    value = " ".join(value.replace("\n", " ").replace("\r", " ").split())
    return value[:limit]


def _age(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def render_conky(snapshot, now):
    """Render the sanitized slow-display summary consumed through execpi."""
    mode = {"off": "OFF", "tailnet": "TAILNET", "lan": "TAILNET + LAN"}.get(
        snapshot.get("mode"), "DEGRADED")
    trust = _safe_text(snapshot.get("trust", "untrusted")).upper()
    rows = list(snapshot.get("sessions") or [])
    lines = [f"${{color1}}REMOTE WATCH${{color2}} · {mode} · {trust}"]
    if not rows:
        lines.append("${color2}No remote sessions in the last 24 hours.")
        return "\n".join(lines)

    for row in rows[:DISPLAY_LIMIT]:
        live = bool(row.get("live"))
        marker = "${color4}LIVE${color}" if live else "${color2}ENDED${color}"
        identity = _safe_text(row.get("identity") or "unknown", 32)
        account = _safe_text(row.get("account") or "?", 16)
        source = _safe_text(row.get("source") or "unknown", 24)
        auth = _safe_text(row.get("auth") or "unknown", 28)
        until = now if live else float(row.get("ended", now))
        duration = _age(until - float(row.get("started", until)))
        lines.append(f"{marker} {account} ← {identity} · {source} · {duration}")
        process = safe_process_chain(row.get("processes", []))
        detail = " → ".join(process) if process else "no process detail"
        lines.append(f"${{color2}}  {auth} · {_safe_text(detail, 68)}")
    if len(rows) > DISPLAY_LIMIT:
        lines.append(f"${{color5}}+ {len(rows) - DISPLAY_LIMIT} MORE")
    return "\n".join(lines)


def atomic_json(path, value, mode=0o600):
    """Write a JSON document atomically with explicit final permissions."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        temporary.replace(path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
