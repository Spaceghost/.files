"""Serving a network instead of joining one, and talking straight to a peer.

This radio can host and join at the same time, but only on one channel.  The
kernel says so plainly:

    #{ managed } <= 1, #{ AP } <= 1, #{ P2P-client } <= 1, #{ P2P-device } <= 1,
    total <= 4, #channels <= 1

That single line decides the whole design.  A hotspot raised while the machine
is online *must* sit on the channel the uplink is already using; asking for any
other channel does not produce a worse hotspot, it produces a driver that
refuses or an uplink that drops.  So the channel is not really a preference when
connected -- it is read from the association and obeyed.  Only when the machine
is offline is the channel a free choice, and then it is worth choosing well,
which is what the air survey is for.

Nothing here is installed by default.  hostapd and dnsmasq are two small stock
Alpine packages, but they are not on the machine until a hotspot is actually
wanted, so every entry point reports exactly what is missing rather than failing
somewhere deep inside a service script.
"""
from __future__ import annotations

from pathlib import Path
import secrets
import shutil
import subprocess
import time

import wifi
import wifi_join as join
from wifi import WifiError

RUN = Path("/run/oldbook-hotspot")
AP_IFACE = "ap0"
# A range unlikely to collide with whatever the upstream network hands out;
# 192.168.0.0/24 and 192.168.1.0/24 are what most home routers use, and a
# hotspot that overlaps its own uplink routes nothing anywhere.
AP_NETWORK = "10.42.7"
AP_ADDRESS = f"{AP_NETWORK}.1"
NFT_TABLE = "oldbook_hotspot"
REQUIREMENTS = ("hostapd", "dnsmasq")


def missing_tools():
    """Which of the two packages the hotspot needs are not installed."""
    return [name for name in REQUIREMENTS if not shutil.which(name)]


def root_write(path, body):
    """Put a configuration file where only root can have written it."""
    subprocess.run(["doas", "-n", "mkdir", "-p", str(Path(path).parent)],
                   check=False, capture_output=True, text=True)
    result = subprocess.run(["doas", "-n", "tee", str(path)], input=body,
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise WifiError(f"Could not write {path}.", (result.stderr or "").strip())
    subprocess.run(["doas", "-n", "chmod", "600", str(path)],
                   check=False, capture_output=True, text=True)


def root_run(*arguments, check=True, timeout=20):
    result = subprocess.run(["doas", "-n", *[str(a) for a in arguments]],
                            capture_output=True, text=True, timeout=timeout, check=False)
    if check and result.returncode != 0:
        raise WifiError(f"{arguments[0]} failed.",
                        (result.stderr or result.stdout or "").strip())
    return result


def uplink_channel(iface=""):
    """The channel the client association is on, which an AP must match."""
    record = wifi.status(iface)
    frequency = record.get("freq")
    return wifi.channel_of(frequency) if frequency else 0


def choose_channel(preference=None, networks=None, iface=""):
    """Where to put the hotspot, obeying the radio before obeying the preference.

    Returns the channel and the sentence explaining it, because a hotspot that
    silently ignored the configured channel is a hotspot he will think is broken.
    """
    preference = preference or wifi.preferences()
    wanted = (preference.get("hotspot") or {}).get("channel", "auto")
    band = (preference.get("hotspot") or {}).get("band", "2.4")
    live = uplink_channel(iface)
    if live:
        if str(wanted) not in ("auto", "follow") and int(wanted) != live:
            return live, (f"channel {live}, following the uplink; this radio "
                          f"cannot host on {wanted} while connected")
        return live, f"channel {live}, following the uplink"
    if str(wanted) not in ("auto", "follow"):
        return int(wanted), f"channel {wanted}, as configured"
    if networks is None:
        networks = []
    channel = wifi.quietest_channel(networks, band) if networks else (6 if band == "2.4" else 44)
    return channel, f"channel {channel}, the quietest {band} GHz channel the scan heard"


def passphrase(preference=None):
    """The hotspot's password, generated once and then kept.

    A hotspot whose password changes every time it is raised cannot be saved on
    a phone, which defeats the point of having one.
    """
    preference = preference or wifi.preferences()
    hotspot = dict(preference.get("hotspot") or {})
    secret = hotspot.get("passphrase")
    if not secret or len(secret) < 8:
        # Four short words beat twelve random characters when the other end of
        # this is somebody typing it on a phone keyboard.
        alphabet = "abcdefghijkmnopqrstuvwxyz23456789"
        secret = "-".join("".join(secrets.choice(alphabet) for _ in range(4))
                          for _ in range(3))
        hotspot["passphrase"] = secret
        preference["hotspot"] = hotspot
        wifi.save_preferences(preference)
    return secret


def hostapd_config(ssid, channel, secret):
    """hostapd's own words for 'a WPA2 access point on this channel'."""
    return "\n".join((
        f"interface={AP_IFACE}",
        "driver=nl80211",
        f"ssid={ssid}",
        f"channel={channel}",
        # 2.4 GHz channels are 1-14; anything above is the 5 GHz band, which
        # hostapd calls 'a' rather than 'g'.
        f"hw_mode={'g' if channel <= 14 else 'a'}",
        "ieee80211n=1",
        "wmm_enabled=1",
        "auth_algs=1",
        "wpa=2",
        f"wpa_passphrase={secret}",
        "wpa_key_mgmt=WPA-PSK",
        "rsn_pairwise=CCMP",
        # Clients on a shared hotspot have no business reaching each other.
        "ap_isolate=1",
        "",
    ))


def dnsmasq_config():
    return "\n".join((
        f"interface={AP_IFACE}",
        "bind-interfaces",
        # Answering DNS or DHCP on the uplink would make this machine a rogue
        # server on somebody else's network.
        "except-interface=lo",
        f"dhcp-range={AP_NETWORK}.10,{AP_NETWORK}.60,12h",
        f"dhcp-option=3,{AP_ADDRESS}",
        f"dhcp-option=6,{AP_ADDRESS}",
        "no-hosts",
        "no-resolv",
        "server=1.1.1.1",
        "server=9.9.9.9",
        f"pid-file={RUN}/dnsmasq.pid",
        "",
    ))


def nft_ruleset(uplink):
    """Masquerade the hotspot's traffic out of the uplink, in its own table.

    A separate table is not tidiness: OpenSnitch owns its own nftables tables
    and flushing the ruleset wholesale would take the firewall down with it.
    This table can be added and deleted without touching anything else.
    """
    return "\n".join((
        f"table inet {NFT_TABLE} {{",
        "  chain postrouting {",
        "    type nat hook postrouting priority srcnat; policy accept;",
        f"    oifname \"{uplink}\" ip saddr {AP_NETWORK}.0/24 masquerade",
        "  }",
        "  chain forward {",
        "    type filter hook forward priority filter; policy accept;",
        f"    iifname \"{AP_IFACE}\" oifname \"{uplink}\" accept",
        f"    iifname \"{uplink}\" oifname \"{AP_IFACE}\" ct state related,established accept",
        "  }",
        "}",
        "",
    ))


def running():
    """Whether a hotspot this module raised is still up."""
    return (RUN / "hostapd.pid").exists() and AP_IFACE in interfaces()


def interfaces():
    try:
        return [node.name for node in Path("/sys/class/net").iterdir()]
    except OSError:
        return []


def start(preference=None, networks=None, iface=""):
    """Raise the access point beside the client association."""
    preference = preference or wifi.preferences()
    iface = iface or wifi.interface()
    absent = missing_tools()
    if absent:
        raise WifiError(
            "The hotspot needs software that is not installed yet.",
            f"Missing: {', '.join(absent)}. Install with: doas apk add {' '.join(absent)}")
    if running():
        raise WifiError("The hotspot is already up.", "Stop it before raising it again.")
    hotspot = preference.get("hotspot") or {}
    ssid = hotspot.get("ssid") or "Ghost Planet"
    channel, why = choose_channel(preference, networks, iface)
    secret = passphrase(preference)

    root_run("mkdir", "-p", str(RUN))
    # A virtual AP interface beside the station one; the combination table
    # permits exactly one of each.
    if AP_IFACE not in interfaces():
        root_run("iw", "dev", iface, "interface", "add", AP_IFACE, "type", "__ap")
    root_write(RUN / "hostapd.conf", hostapd_config(ssid, channel, secret))
    root_write(RUN / "dnsmasq.conf", dnsmasq_config())

    root_run("ip", "address", "flush", "dev", AP_IFACE, check=False)
    root_run("ip", "address", "add", f"{AP_ADDRESS}/24", "dev", AP_IFACE)
    root_run("ip", "link", "set", AP_IFACE, "up")
    root_run("sysctl", "-w", "net.ipv4.ip_forward=1")

    root_run("hostapd", "-B", "-P", str(RUN / "hostapd.pid"), str(RUN / "hostapd.conf"))
    root_run("dnsmasq", "-C", str(RUN / "dnsmasq.conf"))
    # Only masquerade if there is somewhere to masquerade to; an offline hotspot
    # is still useful for moving files between two laptops.
    shared = bool(join.address_of(iface))
    if shared:
        result = subprocess.run(["doas", "-n", "nft", "-f", "-"],
                                input=nft_ruleset(iface), capture_output=True,
                                text=True, check=False)
        if result.returncode != 0:
            shared = False
    return {"ssid": ssid, "channel": channel, "why": why, "passphrase": secret,
            "address": AP_ADDRESS, "shared": shared, "interface": AP_IFACE}


def stop(iface=""):
    """Take it all down, in the reverse order it went up, forgiving what is already gone."""
    told = []
    subprocess.run(["doas", "-n", "nft", "delete", "table", "inet", NFT_TABLE],
                   capture_output=True, text=True, check=False)
    for name in ("dnsmasq", "hostapd"):
        pid_file = RUN / f"{name}.pid"
        try:
            pid = int(pid_file.read_text().strip())
        except (OSError, ValueError):
            continue
        subprocess.run(["doas", "-n", "kill", str(pid)], capture_output=True,
                       text=True, check=False)
        told.append(f"{name} stopped")
    time.sleep(0.3)
    if AP_IFACE in interfaces():
        root_run("ip", "link", "set", AP_IFACE, "down", check=False)
        root_run("iw", "dev", AP_IFACE, "del", check=False)
        told.append("access point interface removed")
    subprocess.run(["doas", "-n", "rm", "-rf", str(RUN)], capture_output=True,
                   text=True, check=False)
    return told or ["nothing was running"]


def clients():
    """Who is on the hotspot, by lease rather than by association.

    The DHCP lease carries the name the device calls itself, which is far more
    use than a hardware address when the question is 'is my phone on yet'.
    """
    found = []
    for path in (RUN / "dnsmasq.leases", Path("/var/lib/misc/dnsmasq.leases")):
        try:
            body = path.read_text()
        except OSError:
            continue
        for line in body.splitlines():
            fields = line.split()
            if len(fields) >= 4:
                found.append({"mac": fields[1], "address": fields[2],
                              "name": fields[3] if fields[3] != "*" else ""})
        break
    return found


# --- Wi-Fi Direct -----------------------------------------------------------
# A peer-to-peer link needs no access point at all, and the combination table
# allows it alongside the client association.  It is genuinely useful for moving
# something between two laptops in a room with no trustworthy network, and it is
# also fiddly and rarely wanted, which is why it lives at the far end of the
# menus rather than beside the everyday list.

def p2p_find(seconds=8, iface=""):
    wifi.wpa("p2p_find", int(seconds), iface=iface)
    time.sleep(min(seconds, 10))
    return p2p_peers(iface)


def p2p_peers(iface=""):
    """Every peer discovery has heard from, with whatever it says about itself."""
    try:
        body = wifi.wpa("p2p_peers", iface=iface, timeout=6)
    except (WifiError, OSError):
        return []
    peers = []
    for address in body.split():
        address = address.strip()
        if not address or ":" not in address:
            continue
        entry = {"address": address, "name": "", "type": ""}
        try:
            detail = wifi.wpa("p2p_peer", address, iface=iface, timeout=6)
            for line in detail.splitlines():
                if line.startswith("device_name="):
                    entry["name"] = line.partition("=")[2].strip()
                elif line.startswith("pri_dev_type="):
                    entry["type"] = line.partition("=")[2].strip()
        except (WifiError, OSError):
            pass
        peers.append(entry)
    return peers


def p2p_stop(iface=""):
    for command in ("p2p_stop_find", "p2p_flush"):
        try:
            wifi.wpa(command, iface=iface, timeout=6)
        except (WifiError, OSError):
            pass


def p2p_connect(address, method="pbc", pin="", iface=""):
    """Join a peer.  'pbc' is the push-button both ends confirm; a PIN is typed."""
    arguments = ["p2p_connect", address]
    arguments += [pin, "keypad"] if method == "pin" and pin else ["pbc"]
    return wifi.wpa(*arguments, iface=iface, timeout=20)
