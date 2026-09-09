"""Joining, leaving, and what the desktop does about where it has just arrived.

Reading the air is one thing; changing which network the machine is on is
another, and this is the half that can strand him.  Two rules shape it.

The first is that the lease client is signalled, never replaced.  ifupdown-ng
started one udhcpc at boot and the radio documentation is explicit that stopping
it is not a neutral ownership transfer; two clients on one interface fight over
the same lease and the loser leaves a stale address behind.  So a new network
gets a release and a renew sent to the client that already exists.

The second is that a refusal must arrive with its reason.  wpa_supplicant does
not answer 'why did that fail', so the reason is recovered from two places that
do know: the network's own flags, which carry TEMP-DISABLED after an
authentication failure, and the system log, which carries the daemon's own
sentence -- 'pre-shared key may be incorrect', 'authentication timed out'.  A
notification saying 'could not connect' when the daemon said WRONG_KEY has
thrown away the only useful part of the event.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.request

import wifi
from wifi import WifiError

STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "oldbook"
LOGBOOK = STATE / "wifi-logbook.json"
MESSAGES = Path("/var/log/messages")

# wpa_supplicant's own vocabulary for why an association did not happen, in the
# order we would rather report them: the specific beats the general.
REASONS = (
    ("pre-shared key may be incorrect", "The password was not accepted."),
    ("WRONG_KEY", "The password was not accepted."),
    ("CONN_FAILED", "The access point refused the connection."),
    ("AUTH_TIMEOUT", "The access point stopped answering during authentication."),
    ("association timed out", "The access point did not complete the association."),
    ("no suitable network", "That network was not on the air when we looked."),
)

# How wpa_supplicant names the state it reaches when everything worked.
CONNECTED = "COMPLETED"


def state_dir():
    STATE.mkdir(parents=True, exist_ok=True)
    return STATE


def logbook():
    """Everything the desktop remembers about where it has been."""
    try:
        stored = json.loads(LOGBOOK.read_text())
    except (OSError, ValueError):
        return {}
    return stored if isinstance(stored, dict) else {}


def write_logbook(entries):
    try:
        state_dir()
        temporary = LOGBOOK.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n")
        os.chmod(temporary, 0o600)
        temporary.replace(LOGBOOK)
    except OSError:
        pass


def record_arrival(ssid, address="", bssid=""):
    """Note that we got here, so the picker can say when we were last here.

    'Joined four times, last seen three weeks ago' is the line that tells him a
    network in the list is one of his rather than a stranger with a familiar
    name, which is exactly the confusion an evil twin access point trades on.
    """
    if not ssid:
        return {}
    entries = logbook()
    entry = dict(entries.get(ssid) or {})
    now = time.time()
    entry["last_seen"] = now
    entry.setdefault("first_seen", now)
    entry["joins"] = int(entry.get("joins") or 0) + 1
    if address:
        entry["last_address"] = address
    if bssid:
        entry["last_bssid"] = bssid
    entries[ssid] = entry
    write_logbook(entries)
    return entry


def since(moment):
    """A rough, readable age.  Precision past 'weeks' helps nobody choosing a network."""
    if not moment:
        return ""
    seconds = max(0, time.time() - float(moment))
    for size, name in ((31536000, "year"), (2592000, "month"), (604800, "week"),
                       (86400, "day"), (3600, "hour"), (60, "minute")):
        if seconds >= size:
            count = int(seconds // size)
            return f"{count} {name}{'s' if count != 1 else ''} ago"
    return "just now"


def dhcp_pid(iface=""):
    """The lease client ifupdown-ng started, if it is still the one running."""
    iface = iface or wifi.interface()
    for candidate in (Path(f"/run/udhcpc.{iface}.pid"), Path(f"/var/run/udhcpc.{iface}.pid")):
        try:
            pid = int(candidate.read_text().strip())
        except (OSError, ValueError):
            continue
        # A pid file outlives the process that wrote it.  Confirm the process is
        # both alive and actually a lease client before signalling it.
        try:
            command = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")
        except OSError:
            continue
        if "udhcpc" in command:
            return pid
    return 0


def renew_lease(iface="", fresh=True):
    """Make the existing lease client ask again, releasing first on a new network.

    SIGUSR2 releases and SIGUSR1 renews.  On a network we have just switched to,
    the old lease is not merely stale but wrong -- it belongs to a different
    subnet -- so it is released before the new one is requested.
    """
    iface = iface or wifi.interface()
    pid = dhcp_pid(iface)
    if not pid:
        # No client to signal.  One-shot rather than persistent, so we are not
        # quietly installing a second permanent owner of the interface.
        result = subprocess.run(["doas", "-n", "udhcpc", "-q", "-n", "-t", "5", "-i", iface],
                                capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise WifiError("No address could be obtained.",
                            (result.stderr or result.stdout or "").strip())
        return "one-shot"
    try:
        if fresh:
            subprocess.run(["doas", "-n", "kill", "-USR2", str(pid)], check=False,
                           capture_output=True, text=True)
            time.sleep(0.4)
        result = subprocess.run(["doas", "-n", "kill", "-USR1", str(pid)],
                                capture_output=True, text=True, check=False)
    except OSError as error:
        raise WifiError("The lease client could not be signalled.", str(error))
    if result.returncode != 0:
        raise WifiError("The lease client refused the renew signal.",
                        (result.stderr or "").strip())
    return f"signalled pid {pid}"


def address_of(iface=""):
    """The global address currently on the interface, if any."""
    iface = iface or wifi.interface()
    try:
        data = subprocess.run(["ip", "-j", "address", "show", "dev", iface],
                              capture_output=True, text=True, timeout=3, check=False)
        for item in json.loads(data.stdout or "[]"):
            for entry in item.get("addr_info", []):
                if entry.get("scope") == "global" and entry.get("family") == "inet":
                    return entry.get("local", "")
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return ""


def log_reason():
    """The supplicant's own last word about a failure, from the system log.

    /var/log/messages is root:wheel and he is in wheel, so this needs no
    escalation.  Only the recent tail is considered: an hour-old WRONG_KEY from
    a different network would be worse than saying nothing.
    """
    try:
        body = MESSAGES.read_text(errors="replace")
    except OSError:
        return ""
    recent = body.splitlines()[-400:]
    for line in reversed(recent):
        if "wpa_supplicant" not in line:
            continue
        for needle, sentence in REASONS:
            if needle in line:
                return sentence
        if "CTRL-EVENT-DISCONNECTED" in line and "reason=" in line:
            match = re.search(r"reason=(\d+)", line)
            if match:
                return f"The access point disconnected us (reason {match.group(1)})."
    return ""


def failure_reason(network_id=None, iface=""):
    """Why the last attempt did not take, in the most specific words available."""
    told = log_reason()
    if told:
        return told
    if network_id is not None:
        for entry in raw_network_flags(iface):
            if entry["id"] == network_id and "TEMP-DISABLED" in entry["flags"]:
                return ("The network was temporarily disabled after a failed "
                        "authentication, which usually means the password is wrong.")
    return ""


def raw_network_flags(iface=""):
    """Saved networks with their raw flag string, which `saved` deliberately folds."""
    try:
        body = wifi.wpa("list_networks", iface=iface, timeout=6)
    except (WifiError, OSError):
        return []
    entries = []
    for line in body.splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) >= 3 and fields[0].strip().isdigit():
            entries.append({"id": int(fields[0]), "ssid": fields[1],
                            "flags": fields[3] if len(fields) > 3 else ""})
    return entries


def quote(value):
    """A value the supplicant will read back as the string we meant.

    Network names genuinely contain spaces, quotes and backslashes.  This is
    never interpolated into a shell -- wpa_cli is executed as an argument list --
    but it is interpolated into the supplicant's own config grammar, which has
    its own escaping and will silently truncate a name at an unescaped quote.
    """
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def set_field(network_id, key, value, iface="", quoted=True):
    wifi.wpa("set_network", network_id, key, quote(value) if quoted else str(value), iface=iface)


def create(ssid, security="psk", secret="", identity="", hidden=False,
           mac="", eap="PEAP", ca_cert="", iface=""):
    """Write one network block and return its id, without enabling it yet.

    Nothing is saved to disk here.  A network that fails to authenticate should
    not be left behind in wpa_supplicant.conf as a permanent guess at a
    password, so the caller commits it only once it has worked.
    """
    identifier = int(wifi.wpa("add_network", iface=iface).strip().splitlines()[-1])
    try:
        set_field(identifier, "ssid", ssid, iface)
        if hidden:
            # Without this the supplicant never probes for the name, and a
            # network that does not broadcast is simply never found.
            set_field(identifier, "scan_ssid", 1, iface, quoted=False)
        if security == "open":
            set_field(identifier, "key_mgmt", "NONE", iface, quoted=False)
        elif security == "wep":
            set_field(identifier, "key_mgmt", "NONE", iface, quoted=False)
            set_field(identifier, "wep_key0", secret, iface)
            set_field(identifier, "wep_tx_keyidx", 0, iface, quoted=False)
        elif security == "eap":
            set_field(identifier, "key_mgmt", "WPA-EAP", iface, quoted=False)
            set_field(identifier, "eap", eap, iface, quoted=False)
            set_field(identifier, "identity", identity, iface)
            set_field(identifier, "password", secret, iface)
            # PEAP and TTLS both carry an inner method; MSCHAPV2 is what almost
            # every campus and conference network expects.
            set_field(identifier, "phase2", "auth=MSCHAPV2", iface)
            if ca_cert:
                set_field(identifier, "ca_cert", ca_cert, iface)
        elif security == "sae":
            set_field(identifier, "key_mgmt", "SAE", iface, quoted=False)
            set_field(identifier, "ieee80211w", 2, iface, quoted=False)
            set_field(identifier, "psk", secret, iface)
        else:
            set_field(identifier, "psk", secret, iface)
        if mac:
            apply_mac_policy(identifier, mac, iface)
    except WifiError:
        # A half-written network block is worse than none: it will sit in the
        # list looking joinable and fail every time.
        try:
            wifi.wpa("remove_network", identifier, iface=iface)
        except (WifiError, OSError):
            pass
        raise
    return identifier


def apply_mac_policy(network_id, mac, iface=""):
    """Ask for a randomised hardware address, and let the caller hear a refusal.

    The value 3 is a per-network random address that stays the same for that
    network: a captive portal sign-in survives, and the DHCP server sees one
    stable client, while a different venue sees an unrelated machine.  Whether
    the driver honours any of this is a separate question -- brcmfmac is a
    FullMAC part and may simply say no -- which is why the refusal is raised
    rather than swallowed.
    """
    value = {"random": 3, "random-always": 1, "permanent": 0}.get(mac)
    if value is None:
        return False
    set_field(network_id, "mac_addr", value, iface, quoted=False)
    return True


def wait_for_connection(iface="", timeout=25.0, network_id=None):
    """Poll until the supplicant says COMPLETED, or explain why it never will."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = wifi.status(iface)
        if record.get("wpa_state") == CONNECTED:
            return record
        for entry in raw_network_flags(iface):
            if network_id is not None and entry["id"] == network_id and "TEMP-DISABLED" in entry["flags"]:
                raise WifiError("The network refused us.",
                                failure_reason(network_id, iface) or
                                "wpa_supplicant disabled it after a failed authentication.")
        time.sleep(0.5)
    raise WifiError("The connection did not complete in time.",
                    failure_reason(network_id, iface) or
                    f"The supplicant is still in state {wifi.status(iface).get('wpa_state', 'unknown')}.")


def activate(network_id, iface="", timeout=25.0):
    """Bring one saved network up, then hand the others back their candidacy.

    `select_network` does not merely prefer the chosen network, it disables
    every other one.  That is the behaviour we want for the join itself -- it
    stops the supplicant wandering back to a stronger network mid-connection --
    but it must not outlive it.  Committed to disk in that state, the first
    cafe he joined would permanently disable his home network, and he would
    come home to a laptop that no longer knew how to associate.
    """
    wifi.wpa("select_network", network_id, iface=iface)
    try:
        record = wait_for_connection(iface, timeout, network_id)
    finally:
        try:
            wifi.wpa("enable_network", "all", iface=iface)
        except (WifiError, OSError):
            pass
    renew_lease(iface, fresh=True)
    return record


def commit(iface=""):
    """Persist the supplicant's in-memory list to its configuration file.

    Only ever called after a network has actually worked, so the file does not
    accumulate failed guesses.
    """
    wifi.wpa("save_config", iface=iface)


def forget(network_id, ssid="", iface=""):
    wifi.wpa("remove_network", network_id, iface=iface)
    commit(iface)
    if ssid:
        entries = logbook()
        if ssid in entries:
            del entries[ssid]
            write_logbook(entries)
    return True


def disconnect(iface=""):
    wifi.wpa("disconnect", iface=iface)


def reconnect(iface=""):
    wifi.wpa("reconnect", iface=iface)


def portal_state(preference=None, timeout=4.0):
    """Whether something is intercepting the connection.

    A captive portal answers a request that should have returned a known short
    body with its own sign-in page instead, so the check is 'did I get back
    exactly what I asked for'.  This makes one real request, which OpenSnitch
    will very likely ask about the first time; that prompt is the firewall
    working, not a fault.
    """
    preference = preference or wifi.preferences()
    if not preference.get("portal_check", True):
        return {"state": "unchecked", "detail": "The portal check is switched off."}
    url = preference.get("portal_url") or wifi.DEFAULTS["portal_url"]
    expect = preference.get("portal_expect") or wifi.DEFAULTS["portal_expect"]
    request = urllib.request.Request(url, headers={"User-Agent": "oldbook-wifi"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            body = answer.read(2048).decode(errors="replace").strip()
            location = answer.geturl()
    except urllib.error.HTTPError as error:
        return {"state": "portal", "detail": f"The check returned HTTP {error.code}.",
                "url": getattr(error, "url", url)}
    except (urllib.error.URLError, OSError, ValueError) as error:
        return {"state": "offline", "detail": f"The check could not be made: {error}."}
    if expect in body:
        return {"state": "open", "detail": "The connection reaches the internet."}
    return {"state": "portal",
            "detail": "Something answered in place of the check; this network wants a sign-in.",
            "url": location}


def shields_for(ssid, preference=None):
    """What posture this network is held at, and what that implies."""
    preference = preference or wifi.preferences()
    trust = wifi.trust_of(ssid, preference)
    shields = (preference.get("shields") or {}).get(trust) or {}
    return trust, shields


def priorities(iface=""):
    """Each saved network's auto-join priority, defaulting to zero."""
    found = {}
    for entry in wifi.saved(iface):
        try:
            value = wifi.wpa("get_network", entry["id"], "priority", iface=iface).splitlines()[-1]
            found[entry["id"]] = int(value.strip())
        except (WifiError, OSError, ValueError):
            found[entry["id"]] = 0
    return found


def promote(network_id, iface=""):
    """Put one network at the head of the auto-join order.

    wpa_supplicant picks among the networks it can see by priority, highest
    first, so 'prefer this one' is one number rather than a reordering.  Setting
    it one above the current maximum keeps the rest of the order intact, which
    matters because the list is his and reshuffling it would be a surprise.
    """
    highest = max(priorities(iface).values(), default=0)
    wifi.wpa("set_network", network_id, "priority", str(highest + 1), iface=iface)
    commit(iface)
    return highest + 1


def import_saved(source):
    """Restore the postures and notes an export carried, but never a password.

    An export deliberately holds no secrets, so this cannot recreate a network
    block that would associate.  What it can restore is everything the desktop
    decided about those networks -- which are home ground and which are public
    air -- so a second laptop starts out holding them the same way rather than
    treating his own network as a stranger's.  The count of networks still
    needing a password is returned, because that is the part he has to do.
    """
    document = json.loads(Path(source).read_text())
    entries = document.get("networks") or []
    known = {entry["ssid"] for entry in wifi.saved()}
    restored = pending = 0
    for entry in entries:
        ssid = (entry or {}).get("ssid")
        if not ssid:
            continue
        fields = {key: entry[key] for key in ("trust", "notes")
                  if entry.get(key)}
        if fields:
            wifi.remember(ssid, **fields)
            restored += 1
        if ssid not in known:
            pending += 1
    return restored, pending


def export_saved(destination, iface=""):
    """Write the saved list somewhere the other laptops can read it.

    Secrets are deliberately not included.  wpa_supplicant will not read a psk
    back out of a network block, and a file of plaintext passwords travelling
    between machines is a worse problem than retyping one.
    """
    entries = []
    for entry in wifi.saved(iface):
        remembered = (wifi.preferences().get("networks") or {}).get(entry["ssid"]) or {}
        entries.append({"ssid": entry["ssid"], "trust": remembered.get("trust", ""),
                        "notes": remembered.get("notes", "")})
    document = {"networks": entries, "exported": time.time(), "secrets": False}
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    os.chmod(path, 0o600)
    return len(entries)
