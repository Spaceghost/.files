"""What is on the air, and what to join.

Every other network surface on this desktop is deliberately passive: it reads
the kernel's counters and the routing table and says so, because a status line
that scans is a status line announcing to the room that you are here.  This
module is the one place allowed to transmit, and it only does so when he asks.
Nothing here runs on a timer.  `status` and `describe` read the supplicant's own
association state, which costs nothing and reveals nothing; `scan` is the only
call that puts probe requests in the air, and it exists to answer a menu he has
just opened.

The supplicant is reached through its control socket rather than by rewriting
its configuration file and restarting it.  That distinction matters: a restart
drops the association in use, and on a machine whose only link is this radio
that is the difference between changing networks and losing the session.  The
socket lives under /run/wpa_supplicant owned by root with no group, so every
command goes through `doas`, which this machine already grants the wheel group
without a password.  No new privilege is created here; the existing one is used.

Failures carry the supplicant's own words.  `wpa_cli` answers 'FAIL' and little
else, but the daemon's reason for refusing -- WRONG_KEY, AUTH_TIMEOUT, a driver
that will not randomise a MAC -- is the one piece of information worth having,
and a message saying 'could not connect' throws it away.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import time

HOME = Path.home()
CTRL_DIR = Path("/run/wpa_supplicant")
SUPPLICANT_CONF = Path("/etc/wpa_supplicant/wpa_supplicant.conf")

# Everything ambient on this desktop defaults to off and is opt-in.  The Wi-Fi
# surfaces follow the same rule, so an unwritten preference file means the
# quietest behaviour rather than the most helpful one.
DEFAULTS = {
    "notifications": True,
    "sound": False,
    "logbook": True,
    "portal_check": True,
    "portal_url": "http://detectportal.firefox.com/success.txt",
    "portal_expect": "success",
    "scan_randomization": True,
    "default_trust": "public",
    "shields": {
        "public": {"mac": "random", "bluetooth": "off"},
        "trusted": {"mac": "random", "bluetooth": "keep"},
        "home": {"mac": "permanent", "bluetooth": "keep"},
    },
    "hotspot": {"ssid": "Ghost Planet", "band": "2.4", "channel": "auto"},
    "networks": {},
}

# Signal strength drawn the way the rest of the setup draws a quantity: a fixed
# ramp where every step means something, rather than a number in a sentence.
BARS = ("\U000f092f", "\U000f091f", "\U000f0922", "\U000f0925", "\U000f0928")
# The same ramp with a padlock struck through it, which is how every phone
# distinguishes a network that will ask for a password from one that will not.
# Reaching for the strength glyph alone would make an open network look
# identical to a locked one at a glance, and the open one is the dangerous one.
LOCKED_BARS = ("\U000f092c", "\U000f0921", "\U000f0924", "\U000f0927", "\U000f092a")
OFFLINE_GLYPH = "\U000f092d"
LOCK_GLYPH = "\U000f033e"
BLOCKS = "▁▂▃▄▅▆▇█"
SEGMENTS = ("▰", "▱")

HISTORY_POINTS = 24
TRUSTS = ("home", "trusted", "public")


class WifiError(Exception):
    """A failure that knows why it failed, in the failing tool's own words."""

    def __init__(self, message, cause=""):
        super().__init__(message)
        self.cause = (cause or "").strip()

    def told(self):
        """The sentence to put in front of him: ours, then the tool's own."""
        return f"{self}\n{self.cause}" if self.cause else str(self)


def runtime():
    return Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))


def config_path(name="wifi.json"):
    return Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "oldbook" / name


def preferences():
    """The stored preferences over the defaults, merged one level deep."""
    try:
        stored = json.loads(config_path().read_text())
    except (OSError, ValueError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    merged = dict(DEFAULTS)
    for key, value in stored.items():
        if isinstance(value, dict) and isinstance(DEFAULTS.get(key), dict):
            merged[key] = {**DEFAULTS[key], **value}
        else:
            merged[key] = value
    return merged


def save_preferences(preference):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(preference, indent=2, ensure_ascii=False) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def interface():
    """The first wireless interface the kernel admits to having."""
    try:
        for node in sorted(Path("/sys/class/net").iterdir()):
            if (node / "wireless").is_dir():
                return node.name
    except OSError:
        pass
    return ""


def socket_ready(iface=""):
    """Whether the supplicant is listening for commands at all.

    This is the one failure worth naming precisely, because it is a
    configuration state rather than a fault: a wpa_supplicant.conf with no
    ctrl_interface line associates once at boot and then accepts no instruction
    for the rest of the session.  Nothing can be joined until that is fixed, and
    the fix is a root edit plus a restart, so the menus say exactly that instead
    of reporting a mysteriously empty list.
    """
    iface = iface or interface()
    return bool(iface) and (CTRL_DIR / iface).exists()


def wpa(*arguments, timeout=10, iface=""):
    """One wpa_cli command, run as root, with any refusal preserved."""
    iface = iface or interface()
    if not iface:
        raise WifiError("This machine has no wireless interface.")
    if not socket_ready(iface):
        raise WifiError(
            "wpa_supplicant is not accepting commands.",
            f"Its control socket {CTRL_DIR / iface} does not exist. Add "
            f"'ctrl_interface=DIR=/run/wpa_supplicant' to {SUPPLICANT_CONF} "
            "and restart the service; oldbook-wifi enable-control does both.")
    if not shutil.which("doas"):
        raise WifiError("doas is not installed, so the radio cannot be commanded.")
    try:
        result = subprocess.run(
            ["doas", "-n", "wpa_cli", "-i", iface, *[str(a) for a in arguments]],
            capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise WifiError(f"wpa_cli {arguments[0]} did not answer in {timeout:g}s.",
                        "The supplicant is running but stopped responding.")
    if result.returncode != 0:
        raise WifiError(f"wpa_cli {arguments[0]} was refused.",
                        (result.stderr or result.stdout or "").strip())
    output = result.stdout.strip()
    # wpa_cli exits zero even when the daemon answers FAIL, so the body is the
    # only place a refusal shows up.
    if output.split("\n")[-1].strip() in ("FAIL", "UNKNOWN COMMAND"):
        raise WifiError(f"The supplicant refused '{arguments[0]}'.", output)
    return output


def status(iface=""):
    """The current association, read without transmitting anything."""
    try:
        body = wpa("status", iface=iface, timeout=5)
    except (WifiError, OSError):
        return {}
    record = {}
    for line in body.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            record[key.strip()] = value.strip()
    return record


def channel_of(frequency):
    """The channel a frequency in MHz belongs to, across all three bands."""
    try:
        frequency = int(frequency)
    except (TypeError, ValueError):
        return 0
    if frequency == 2484:
        return 14
    if 2412 <= frequency <= 2472:
        return (frequency - 2407) // 5
    if 5160 <= frequency <= 5885:
        return (frequency - 5000) // 5
    if 5955 <= frequency <= 7115:
        return (frequency - 5950) // 5
    return 0


def band_of(frequency):
    try:
        frequency = int(frequency)
    except (TypeError, ValueError):
        return ""
    if not frequency:
        return ""
    if frequency < 2500:
        return "2.4 GHz"
    if frequency < 5900:
        return "5 GHz"
    return "6 GHz"


def security_of(flags):
    """A readable name for the encryption, and what joining it will need.

    The flags string is the supplicant's own vocabulary -- [WPA2-PSK-CCMP][ESS]
    and its relatives.  The question a menu has to answer is not which cipher
    suite is in use but whether joining needs a password, an identity, or
    nothing at all, because that decides which prompt comes next.
    """
    flags = flags or ""
    if "SAE" in flags and "PSK" in flags:
        name, kind = "WPA2/3 mixed", "psk"
    elif "SAE" in flags:
        name, kind = "WPA3", "sae"
    elif "EAP" in flags:
        name, kind = "WPA2 Enterprise", "eap"
    elif "WPA2" in flags:
        name, kind = "WPA2", "psk"
    elif "WPA" in flags:
        name, kind = "WPA", "psk"
    elif "WEP" in flags:
        name, kind = "WEP", "wep"
    else:
        name, kind = "Open", "open"
    return {"name": name, "kind": kind, "wps": "WPS" in flags,
            # An open network is not merely unencrypted: everything crossing it
            # is readable by everyone else on it, which is the whole reason the
            # shields exist, so it is marked rather than left to inference.
            "open": kind == "open", "enterprise": kind == "eap"}


def quality(dbm):
    """Signal as a step from 0 to 4, with the word for it.

    Received strength is logarithmic and the useful thresholds are not evenly
    spaced: -50 against -60 is barely felt, while -75 against -85 is the
    difference between a working link and a stalled one.
    """
    try:
        dbm = int(float(dbm))
    except (TypeError, ValueError):
        return 0, "unknown"
    if dbm >= -55:
        return 4, "excellent"
    if dbm >= -65:
        return 3, "good"
    if dbm >= -73:
        return 2, "fair"
    if dbm >= -82:
        return 1, "weak"
    return 0, "poor"


def bars(dbm, locked=None):
    """The strength glyph, optionally the padlocked variant of the same step."""
    step, _word = quality(dbm)
    return (LOCKED_BARS if locked else BARS)[step]


# The scale the trace is drawn against, in dBm.  Fixed rather than fitted: see
# `sparkline`.  Roughly seven dB to a block across the range that matters.
SIGNAL_FLOOR, SIGNAL_CEILING = -90, -35


def sparkline(readings):
    """Recent signal as a block ramp, so a drifting link is visible at a glance.

    Drawn from readings the panel already took for its own status line, never
    from anything new: watching the link has to stay free.

    The scale is absolute, not fitted to the readings.  Fitting was the obvious
    thing and it was wrong: a rock-steady excellent link wobbles three or four
    dBm on its own, and stretching that across the full ramp drew a mountain
    range, which reads as an unstable connection and is a lie.  Received signal
    already means something on its own -- -40 is next to the access point, -85
    is about to drop -- so the trace is drawn against that, and a steady link
    is a flat line at the height its quality deserves.  A genuine decline still
    descends, because it is genuinely crossing the scale.
    """
    values = [v for v in readings if isinstance(v, (int, float))]
    if len(values) < 2:
        return ""
    span = SIGNAL_CEILING - SIGNAL_FLOOR
    return "".join(
        BLOCKS[max(0, min(len(BLOCKS) - 1,
                          int((value - SIGNAL_FLOOR) / span * (len(BLOCKS) - 1) + 0.5)))]
        for value in values)


def signal_history(dbm=None):
    """Append one reading and return the recent run, oldest first."""
    path = runtime() / "oldbook-wifi-signal.json"
    try:
        stored = json.loads(path.read_text())
        readings = [v for v in stored if isinstance(v, (int, float))] if isinstance(stored, list) else []
    except (OSError, ValueError):
        readings = []
    if dbm is None:
        return readings
    readings = (readings + [int(dbm)])[-HISTORY_POINTS:]
    try:
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(readings))
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    except OSError:
        pass
    return readings


def link(iface=""):
    """The live association, read with `iw` rather than through the supplicant.

    This is the reading the panel takes every few seconds, so it has to be cheap
    and it has to be safe.  `iw dev <iface> link` is both: it needs no
    privilege, answers in about three milliseconds, transmits nothing, and
    reports more than the control socket does -- it carries the negotiated
    bitrates, which are what actually tell him whether a link with four bars is
    performing.  It also means the whole hover surface keeps working before the
    control interface has ever been opened.
    """
    iface = iface or interface()
    if not iface:
        return {}
    try:
        result = subprocess.run(["iw", "dev", iface, "link"], capture_output=True,
                                text=True, timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        return {}
    body = result.stdout or ""
    if result.returncode != 0 or body.strip().startswith("Not connected"):
        return {}
    record = {}
    first = body.splitlines()[0] if body.splitlines() else ""
    if first.startswith("Connected to "):
        record["bssid"] = first.split()[2]
    for line in body.splitlines()[1:]:
        key, _, value = line.strip().partition(":")
        key, value = key.strip().lower(), value.strip()
        if not value:
            continue
        if key == "ssid":
            record["ssid"] = value
        elif key == "freq":
            try:
                record["frequency"] = int(float(value))
            except ValueError:
                pass
        elif key == "signal":
            try:
                record["signal"] = int(float(value.split()[0]))
            except (ValueError, IndexError):
                pass
        elif key in ("rx bitrate", "tx bitrate"):
            try:
                record[key.replace(" ", "_")] = float(value.split()[0])
            except (ValueError, IndexError):
                pass
    if not record.get("ssid"):
        return {}
    record["channel"] = channel_of(record.get("frequency", 0))
    record["band"] = band_of(record.get("frequency", 0))
    record["step"], record["quality"] = quality(record.get("signal"))
    return record


def association_security(bssid, iface=""):
    """What kind of encryption the current association uses, looked up rarely.

    `iw` will not say, and asking the supplicant costs a `doas` round trip that
    the panel should not be paying every three seconds.  The answer only changes
    when the association does, so it is cached against the access point's
    address and fetched once per arrival.  When the control socket is not open
    the line is simply absent, which is honest: we do not know.
    """
    if not bssid:
        return ""
    cache = runtime() / "oldbook-wifi-assoc.json"
    try:
        stored = json.loads(cache.read_text())
        if isinstance(stored, dict) and stored.get("bssid") == bssid:
            return stored.get("security", "")
    except (OSError, ValueError):
        pass
    if not socket_ready(iface):
        return ""
    security = (status(iface).get("key_mgmt") or "").strip()
    try:
        temporary = cache.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps({"bssid": bssid, "security": security}))
        os.chmod(temporary, 0o600)
        temporary.replace(cache)
    except OSError:
        pass
    return security


def hover_lines(iface=""):
    """The wireless half of the panel's tooltip, or nothing on a wired link.

    Returned as lines for the caller to splice in, so the panel keeps ownership
    of its own layout and this stays the thing that knows about radios.
    """
    record = link(iface)
    if not record:
        return []
    lines = []
    name = record.get("ssid", "")
    security = association_security(record.get("bssid", ""), iface)
    lines.append(f"{name} · {security}" if security else name)
    signal = record.get("signal")
    if signal is not None:
        detail = f"{signal} dBm · {record['quality']}"
        if record.get("band"):
            detail += f" · {record['band']} ch {record['channel']}"
        lines.append(detail)
        trend = sparkline(signal_history(signal))
        if trend:
            lines.append(trend)
    rx, tx = record.get("rx_bitrate"), record.get("tx_bitrate")
    if rx and tx:
        lines.append(f"Link rate {rx:g} down · {tx:g} up Mbit/s")
    return lines


def kernel_signal(iface=""):
    """Association signal straight from /proc: costs nothing, tells no one."""
    iface = iface or interface()
    try:
        body = Path("/proc/net/wireless").read_text()
    except OSError:
        return None
    for line in body.splitlines()[2:]:
        fields = line.split()
        if fields and fields[0].rstrip(":") == iface and len(fields) > 3:
            try:
                return int(float(fields[3].rstrip(".")))
            except ValueError:
                return None
    return None


def raw_results(iface=""):
    try:
        return wpa("scan_results", iface=iface, timeout=6)
    except (WifiError, OSError):
        return ""


def scan(iface="", wait=8.0):
    """Ask the radio what it can hear, and wait for the answer.

    This transmits.  It is the only function here that does, and it is called
    from one place: a menu he has just opened.  The supplicant acknowledges the
    scan immediately and publishes results later, so the wait is for the results
    to change rather than for a fixed interval -- a scan that finishes in a
    second should not cost eight.
    """
    iface = iface or interface()
    before = raw_results(iface)
    try:
        wpa("scan", iface=iface, timeout=6)
    except WifiError as error:
        # A scan refused because one is already in flight is not a failure; its
        # results are exactly what we were about to ask for.
        if "FAIL-BUSY" not in error.cause:
            raise
    deadline = time.monotonic() + wait
    latest = before
    while time.monotonic() < deadline:
        time.sleep(0.4)
        latest = raw_results(iface)
        if latest and latest != before:
            break
    return parse_results(latest)


def parse_results(body):
    """Scan output into one record per network, strongest first.

    The supplicant reports one row per access point, so a network with three of
    them appears three times.  Someone choosing a network wants the network, not
    the radio, so rows are folded by name and the strongest wins -- while the
    count is kept, because 'four access points' is how you tell real coverage
    from one tired router.
    """
    networks = {}
    for line in (body or "").splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) < 5:
            continue
        bssid, frequency, level, flags, ssid = fields[:5]
        if not ssid:
            # A hidden network beacons without a name.  It is real and worth
            # counting, but it cannot be offered as a row to click.
            continue
        try:
            level = int(level)
        except ValueError:
            continue
        record = networks.get(ssid)
        if record is None:
            networks[ssid] = {"ssid": ssid, "bssid": bssid, "signal": level,
                              "frequency": int(frequency) if frequency.lstrip("-").isdigit() else 0,
                              "flags": flags, "security": security_of(flags),
                              "access_points": 1}
        else:
            record["access_points"] += 1
            if level > record["signal"]:
                record.update(bssid=bssid, signal=level, flags=flags,
                              security=security_of(flags),
                              frequency=int(frequency) if frequency.lstrip("-").isdigit() else 0)
    for record in networks.values():
        record["channel"] = channel_of(record["frequency"])
        record["band"] = band_of(record["frequency"])
        record["step"], record["quality"] = quality(record["signal"])
    return sorted(networks.values(), key=lambda r: -r["signal"])


def saved(iface=""):
    """Every network the supplicant has been told to remember."""
    try:
        body = wpa("list_networks", iface=iface, timeout=6)
    except (WifiError, OSError):
        return []
    entries = []
    for line in body.splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) < 3 or not fields[0].strip().isdigit():
            continue
        flags = fields[3] if len(fields) > 3 else ""
        entries.append({"id": int(fields[0]), "ssid": fields[1], "bssid": fields[2],
                        "current": "CURRENT" in flags, "disabled": "DISABLED" in flags})
    return entries


def congestion(networks):
    """How crowded each channel is, for choosing where to put a hotspot.

    A FullMAC radio reports no channel occupancy -- there is no survey to read
    and no monitor mode to fall back on -- so the only honest measure available
    is the one a phone's analyser uses: count what answered the scan and weight
    each by how loudly it arrived, since a distant access point on a channel
    matters far less than one in the same room.
    """
    channels = {}
    for record in networks:
        channel = record.get("channel") or 0
        if not channel:
            continue
        entry = channels.setdefault(channel, {"channel": channel, "count": 0,
                                              "weight": 0.0, "strongest": -100,
                                              "band": record.get("band", "")})
        entry["count"] += 1
        entry["weight"] += max(0.0, (record["signal"] + 100) / 50.0)
        entry["strongest"] = max(entry["strongest"], record["signal"])
    return sorted(channels.values(), key=lambda e: (-e["weight"], e["channel"]))


def quietest_channel(networks, band="2.4"):
    """The least crowded channel worth using, preferring non-overlapping ones.

    On 2.4 GHz only 1, 6 and 11 do not overlap, so a hotspot placed on 3 splits
    the difference badly and interferes with both its neighbours.  Each real
    candidate is scored by what the scan heard on it *and* on the channels
    beside it, because an access point on 4 is very much a hotspot on 6's
    problem.
    """
    loads = {entry["channel"]: entry["weight"] for entry in congestion(networks)}
    candidates = (1, 6, 11) if band == "2.4" else (36, 40, 44, 48, 149, 153, 157, 161)
    reach = 4 if band == "2.4" else 1
    scored = sorted((sum(load for other, load in loads.items()
                         if abs(other - channel) <= reach), channel)
                    for channel in candidates)
    return scored[0][1] if scored else (6 if band == "2.4" else 44)


def trust_of(ssid, preference=None):
    """What posture a network is held at, defaulting to the careful one."""
    preference = preference or preferences()
    entry = (preference.get("networks") or {}).get(ssid) or {}
    trust = entry.get("trust")
    return trust if trust in TRUSTS else preference.get("default_trust", "public")


def remember(ssid, **fields):
    """Record something about a network without disturbing the rest of the file."""
    preference = preferences()
    networks = dict(preference.get("networks") or {})
    entry = dict(networks.get(ssid) or {})
    entry.update(fields)
    networks[ssid] = entry
    preference["networks"] = networks
    save_preferences(preference)
    return preference
