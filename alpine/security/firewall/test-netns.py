#!/usr/bin/env python3
"""Exercise real packet policy in two disposable namespaces; never use host net."""
import argparse
import copy
import http.server
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import time


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs)


def serve():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"mbp-intel-firewall-test\n")

        def log_message(self, *args):
            pass

    # Interfaces are configured after the namespace process has been started.
    while not Path(sys.argv[2]).exists():
        time.sleep(0.05)
    class IPv6Server(http.server.HTTPServer):
        address_family = socket.AF_INET6

        def server_bind(self):
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            super().server_bind()

    for port in (18080, 443):
        ipv6 = IPv6Server(("::", port), Handler)
        threading.Thread(target=ipv6.serve_forever, daemon=True).start()
    https_port = http.server.HTTPServer(("0.0.0.0", 443), Handler)
    threading.Thread(target=https_port.serve_forever, daemon=True).start()
    def udp_server(family, bind):
        with socket.socket(family, socket.SOCK_DGRAM) as sock:
            if family == socket.AF_INET6:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            sock.bind((bind, 18082))
            while True:
                data, peer = sock.recvfrom(4096)
                sock.sendto(data, peer)

    for family, bind in ((socket.AF_INET, "0.0.0.0"), (socket.AF_INET6, "::")):
        threading.Thread(target=udp_server, args=(family, bind), daemon=True).start()
    ipv4 = http.server.HTTPServer(("0.0.0.0", 18080), Handler)
    Path(sys.argv[2] + ".listening").touch()
    ipv4.serve_forever()


def probe(allowed, ipv6=False, port=18080, uid=None):
    host = "[2001:db8:1::2]" if ipv6 else "192.0.2.2"
    result = None
    try:
        result = subprocess.run(
            ["curl", "--disable", "--noproxy", "*", "--silent", "--fail", "--max-time", "2",
             f"http://{host}:{port}/"], text=True, capture_output=True, timeout=3,
            **({"user": uid, "group": uid, "extra_groups": ()} if uid is not None else {}))
        ok = result.returncode == 0 and "mbp-intel-firewall-test" in result.stdout
    except subprocess.TimeoutExpired:
        ok = False
    assert ok == allowed, f"curl expected {'allow' if allowed else 'deny'}: {result}"


def probe_python_denied(port=18080, uid=None):
    result = subprocess.run(
        [sys.executable, "-c", f"import socket; socket.create_connection(('192.0.2.2',{port}),1)"],
        capture_output=True, timeout=2,
        **({"user": uid, "group": uid, "extra_groups": ()} if uid is not None else {}))
    assert result.returncode != 0, "unapproved Python process was allowed"


def probe_udp(allowed, ipv6=False):
    host = "2001:db8:1::2" if ipv6 else "192.0.2.2"
    code = ("import socket,sys; "
            "s=socket.socket(socket.AF_INET6 if ':' in sys.argv[1] else socket.AF_INET,socket.SOCK_DGRAM); "
            "s.settimeout(1); s.connect((sys.argv[1],18082)); "
            "s.send(b'mbp-intel-udp'); assert s.recv(32)==b'mbp-intel-udp'")
    result = subprocess.run([sys.executable, "-c", code, host], capture_output=True, timeout=2)
    assert (result.returncode == 0) == allowed, f"UDP expected allow={allowed}, ipv6={ipv6}: {result.stderr!r}"


def generated_rule_probes(base, work, rules, results):
    """Test generated policy unchanged, using plain HTTP on its real TCP 443 port."""
    uid = 65534
    path = str(Path(shutil.which("curl")).resolve())
    staged = work / "bootstrap"
    run(sys.executable, str(base / "bootstrap-rules"), "--uid", str(uid),
        "--executable", path, "--resolver", "192.0.2.2", "--resolver", "2001:db8:1::2",
        "--output", str(staged))
    generated = sorted((staged / "rules").glob("*.json"))
    assert len(generated) == 3
    for source in generated:
        shutil.copyfile(source, rules / source.name)
    time.sleep(1)
    for ipv6 in (False, True):
        probe(True, ipv6=ipv6, port=443, uid=uid)
        probe(False, ipv6=ipv6, port=443, uid=0)
        probe(False, ipv6=ipv6, port=18080, uid=uid)
    probe_python_denied(port=443, uid=uid)
    results.append("generated HTTPS rules allow exact executable and UID on TCP 443 only")
    results.append("generated HTTPS rules deny wrong UID, different executable and wrong port")

    https = next(source for source in generated if source.name.endswith("-https.json"))
    original = json.loads(https.read_text())
    mismatched = copy.deepcopy(original)
    checksum = next(item for item in mismatched["operator"]["list"]
                    if item["operand"] == "process.hash.md5")
    checksum["data"] = "0" * 32

    def replace_rule(value):
        # OpenSnitch 1.8.0 watches WRITE/REMOVE, not rename-over-existing.
        # Keep this controlled mutation inside the disposable namespace test.
        (rules / https.name).write_text(json.dumps(value))
        time.sleep(1)

    replace_rule(mismatched)
    for ipv6 in (False, True):
        probe(False, ipv6=ipv6, port=443, uid=uid)
    results.append("generated HTTPS rules deny an incorrect populated executable checksum")
    replace_rule(original)
    for ipv6 in (False, True):
        probe(True, ipv6=ipv6, port=443, uid=uid)
    results.append("generated HTTPS checksum rule restores access after exact hash is restored")
    for source in generated:
        (rules / source.name).unlink()
    time.sleep(1)
    probe(False, port=443, uid=uid)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", required=True, type=Path)
    parser.add_argument("--isolated", action="store_true")
    args = parser.parse_args()
    if not args.isolated:
        assert os.geteuid() == 0, "run with doas; tests immediately enter a network namespace"
        env = dict(os.environ, MBP_INTEL_TEST_HOST_NET=os.readlink("/proc/self/ns/net"))
        result = subprocess.run(
            ["unshare", "--net", sys.executable, __file__, "--isolated", "--daemon", str(args.daemon.resolve())],
            env=env)
        raise SystemExit(result.returncode)
    assert os.environ["MBP_INTEL_TEST_HOST_NET"] != os.readlink("/proc/self/ns/net"), "refusing host network"
    base = Path(__file__).resolve().parent
    processes = []
    results = []
    with tempfile.TemporaryDirectory(prefix="mbp-intel-firewall-test-") as name:
        work = Path(name)
        try:
            server = subprocess.Popen(["unshare", "--net", sys.executable, __file__, "serve", str(work / "ready")])
            processes.append(server)
            for _ in range(100):
                if os.readlink(f"/proc/{server.pid}/ns/net") != os.readlink("/proc/self/ns/net"):
                    break
                time.sleep(0.02)
            assert server.poll() is None
            run("ip", "link", "add", "client0", "type", "veth", "peer", "name", "server0")
            run("ip", "link", "set", "server0", "netns", str(server.pid))
            run("ip", "addr", "add", "192.0.2.1/24", "dev", "client0")
            run("ip", "addr", "add", "2001:db8:1::1/64", "dev", "client0", "nodad")
            run("ip", "link", "set", "client0", "up")
            run("ip", "link", "set", "lo", "up")
            for cmd in (("ip", "addr", "add", "192.0.2.2/24", "dev", "server0"),
                        ("ip", "addr", "add", "2001:db8:1::2/64", "dev", "server0", "nodad"),
                        ("ip", "link", "set", "server0", "up"),
                        ("ip", "link", "set", "lo", "up")):
                run("nsenter", f"--net=/proc/{server.pid}/ns/net", *cmd)
            (work / "ready").touch()
            for _ in range(200):
                assert server.poll() is None, "namespace test server exited before readiness"
                if (work / "ready.listening").exists():
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("namespace test server did not report bound listeners")
            probe(True)
            probe(True, ipv6=True)
            probe_udp(True)
            probe_udp(True, ipv6=True)
            probe(True, port=443, uid=65534)
            probe(True, port=443, uid=65534, ipv6=True)
            results.append("baseline namespace connectivity")
            run("nft", "--check", "--file", str(base / "mbp-intel.nft"))
            run("nft", "--file", str(base / "mbp-intel.nft"))
            probe(False)
            probe(False, ipv6=True)
            probe_udp(False)
            probe_udp(False, ipv6=True)
            results.append("new egress denied before daemon starts")

            rules = work / "rules"
            rules.mkdir()
            config = json.loads((base / "default-config.json").read_text())
            config["Rules"]["Path"] = str(rules)
            config["Server"]["Address"] = "unix://" + str(work / "gui.sock")
            config["Server"]["LogFile"] = str(work / "daemon.log")
            config["FwOptions"]["ConfigPath"] = str(base / "system-fw.json")
            config["LogLevel"] = 2
            (work / "config.json").write_text(json.dumps(config))

            def start_daemon():
                output = (work / "stdio.log").open("a")
                proc = subprocess.Popen(
                    [str(args.daemon), "-config-file", str(work / "config.json")],
                    env=dict(os.environ, OPENSNITCH_EXTERNAL_OUTPUT_QUEUE="1"),
                    stdout=output, stderr=output)
                processes.append(proc)
                for _ in range(100):
                    assert proc.poll() is None, (work / "stdio.log").read_text()
                    if Path("/proc/net/netfilter/nfnetlink_queue").exists() and Path("/proc/net/netfilter/nfnetlink_queue").read_text().strip():
                        time.sleep(0.3)
                        return proc
                    time.sleep(0.05)
                raise AssertionError("daemon did not bind NFQUEUE")

            daemon = start_daemon()
            probe(False)
            probe(False, ipv6=True)
            probe_python_denied()
            results.append("default-deny without GUI")
            generated_rule_probes(base, work, rules, results)
            path = str(Path(run("which", "curl").stdout.strip()).resolve())
            allow = {"name": "allow-test-curl", "enabled": True, "precedence": False,
                     "action": "allow", "duration": "always",
                     "operator": {"type": "simple", "operand": "process.path", "data": path}}
            (rules / "allow-test.json").write_text(json.dumps(allow))
            time.sleep(1)
            probe(True)
            probe(True, ipv6=True)
            probe_python_denied()
            results.append("approved curl allowed; different Python executable denied")
            udp_rule = {"name": "allow-test-python-udp", "enabled": True, "precedence": False,
                        "action": "allow", "duration": "always", "operator": {
                            "type": "list", "operand": "list", "list": [
                                {"type": "simple", "operand": "process.path", "data": str(Path(sys.executable).resolve())},
                                {"type": "regexp", "operand": "protocol", "data": "^udp6?$"},
                                {"type": "simple", "operand": "dest.port", "data": "18082"}]}}
            (rules / "allow-udp.json").write_text(json.dumps(udp_rule))
            time.sleep(1)
            probe_udp(True)
            probe_udp(True, ipv6=True)
            probe_python_denied()
            results.append("UDP allow rule is constrained by executable, protocol and port")
            allow["action"] = "deny"
            (rules / "allow-test.json").write_text(json.dumps(allow))
            time.sleep(1)
            probe(False)
            probe(False, ipv6=True)
            results.append("rule changes hot-reload to deny")
            allow["action"] = "allow"
            (rules / "allow-test.json").write_text(json.dumps(allow))
            time.sleep(1)
            probe(True)
            daemon.terminate()
            daemon.wait(timeout=10)
            probe(False)
            probe(False, ipv6=True)
            probe_udp(False)
            probe_udp(False, ipv6=True)
            results.append("persistent gate denies new egress after graceful SIGTERM")
            daemon = start_daemon()
            probe(True)
            daemon.kill()
            daemon.wait(timeout=5)
            probe(False)
            probe(False, ipv6=True)
            probe_udp(False)
            probe_udp(False, ipv6=True)
            results.append("persistent gate denies new egress after SIGKILL")
            ruleset = json.loads(run("nft", "--json", "list", "chain", "inet", "mbp-intel", "output").stdout)
            queues = [expr["queue"] for item in ruleset["nftables"]
                      for expr in item.get("rule", {}).get("expr", []) if "queue" in expr]
            assert len(queues) == 2 and all(q["num"] == 0 and not q.get("flags") for q in queues), queues
            results.append("independent queue remains installed without bypass")
            print(json.dumps({"passed": results, "ip_versions_tested": [4, 6],
                              "transports_tested": ["TCP", "UDP"], "host_network_unchanged": True}, indent=2))
        except Exception:
            for log in (work / "daemon.log", work / "stdio.log"):
                if log.exists():
                    print(log.read_text()[-12000:], file=sys.stderr)
            raise
        finally:
            for proc in reversed(processes):
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        serve()
    else:
        main()
