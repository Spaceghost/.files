// Schema for the "forge" Incus project on bak: an isolated home for a Fossil
// server (serving the ~/.files mirror this laptop's Claude sessions currently
// share directly) plus ephemeral per-session checkout sandboxes, so agent
// sessions stop editing Jack's live checkout side by side with each other.
//
// Modeled on bak's existing bak-control/atlas-infra CUE style (restricted
// project config, #Name regex, per-pool disk quota denial, render-then-apply
// separation -- this file only ever produces a plan; nothing here touches the
// host). This project deliberately does NOT join atlas-infra's GitHub-issue
// coordination workflow: that governs Atlas hardware/worker infra
// specifically, and forge is unrelated to it.
//
// Networking follows the house convention discovered on bak rather than the
// original draft's own per-project bridge: every existing project (codex-*,
// atlas-*) already shares one bridge, `sandbox0` (172.30.240.0/24, NAT'd,
// default ingress reject / egress allow), and cross-project isolation is done
// with per-service network ACLs -- e.g. `bak-portal-desktop`, which allows one
// specific host-side source address into one specific container:port. forge
// reuses `sandbox0` and adds its own narrow ACL the same way, instead of
// minting a new bridge.
//
// Tailnet-only exposure (no public listener, no SSH tunnel): bak's Tailscale
// already runs on the host, not per-container, and `tailscale serve` is
// present but unused (`tailscale serve status` reported no config at plan
// time). `tailscale serve` proxies a path on bak's own tailnet identity
// (bak.bishop-bearded.ts.net) to a local target, refuses to be reachable
// off-tailnet at all, and needs no new authenticated-proxy code -- it is
// exactly the primitive bak-portal already had to hand-build a narrower
// version of for the desktop-only case. The forge ACL only has to admit the
// one hop `tailscale serve`'s local proxy makes from the host, at the
// bridge's own gateway address, into the fossil container's pinned address;
// nothing else may reach it.
package forge

#Name: string & =~"^[a-z][a-z0-9-]{0,39}$"

#Site: {
	host:        "bak"
	project:     #Name
	pool:        #Name // an existing Incus storage pool (not a new zpool)
	network:     #Name // an existing bridge network, reused rather than created
	networkACL:  #Name
	diskQuotaGiB: int & >=4 & <=64
	fossil: {
		instance:  #Name
		cpus:      int & >=1 & <=2
		memoryMiB: int & >=256 & <=1024
		diskGiB:   int & >=2 & <=8
		port:      int & >=1024 & <=65535
		// The bridge's own gateway address, i.e. bak itself -- the only
		// address `tailscale serve`'s local proxy will ever connect from.
		gatewayAddress: string
		// A pinned address for this instance's NIC, so both the ACL
		// destination and the `tailscale serve` target are stable instead
		// of following bridge DHCP. Confirm it's actually free (e.g. via
		// `incus network list-leases <network>`) before applying --
		// this plan does not reserve it.
		address: string
	}
	sandbox: {
		instance:      #Name
		cpus:          int & >=1 & <=4
		memoryMiB:     int & >=512 & <=2048
		diskGiB:       int & >=1 & <=8
		maxConcurrent: int & >=1 & <=6
	}
}
site: #Site

// Every other pool on the host is explicitly zeroed so this project cannot
// touch Jack's other data, matching bak-control's restricted.storage-pools
// pattern (limits.disk.pool.<name> is the supported per-pool quota knob).
otherPools: [...#Name]

incusProject: #IncusProject
#IncusProject: {
	name:        site.project
	description: "Isolated Fossil server + per-session Claude checkout sandboxes"
	config: {
		"features.images":                 "true"
		"features.profiles":               "true"
		"features.networks":               "false" // reuses the existing sandbox0 bridge; mints no network of its own
		"features.storage.volumes":        "true"
		"restricted":                      "true"
		"restricted.containers.privilege": "unprivileged"
		"restricted.containers.nesting":   "block"
		"restricted.containers.lowlevel":  "block"
		"restricted.devices.disk":         "managed"
		"restricted.devices.nic":          "managed"
		"restricted.devices.gpu":          "block"
		"restricted.devices.pci":          "block"
		"restricted.devices.unix-block":   "block"
		"restricted.devices.unix-char":    "block"
		"restricted.devices.unix-hotplug": "block"
		"restricted.networks.access":      site.network
		"limits.containers":               "\(site.sandbox.maxConcurrent + 2)" // +1 fossil server, +1 stopped template
		"limits.virtual-machines":         "0"
		"limits.disk.pool.\(site.pool)":   "\(site.diskQuotaGiB)GiB"
		for p in otherPools {
			"limits.disk.pool.\(p)": "0"
		}
	}
}

// The forge-fossil ACL: the one narrow ingress rule that lets bak's own
// `tailscale serve` process (running on the bridge's gateway address, i.e.
// the host) reach the fossil container's HTTP port. Everything else -- the
// wider tailnet, the LAN, every other project on this bridge -- stays
// rejected by the bridge's own default-ingress-reject, unchanged.
networkACL: #NetworkACL
#NetworkACL: {
	name: site.networkACL
	ingress: [{
		action:           "allow"
		source:           "\(site.fossil.gatewayAddress)/32"
		destination:      "\(site.fossil.address)/32"
		protocol:         "tcp"
		destination_port: "\(site.fossil.port)"
		description:      "tailscale serve on bak proxying to forge-fossil"
	}]
	egress: []
}

// The one long-lived instance: runs `fossil server` bound to its pinned
// address only, reachable from nothing but the ACL rule above.
fossilInstance: #Instance & {
	name: site.fossil.instance
	config: {
		"limits.cpu":     "\(site.fossil.cpus)"
		"limits.memory":  "\(site.fossil.memoryMiB)MiB"
		"boot.autostart": "true"
	}
	devices: {
		root: {type: "disk", path: "/", pool: site.pool, size: "\(site.fossil.diskGiB)GiB"}
		eth0: #RestrictedNIC & {"ipv4.address": site.fossil.address}
	}
}

// The template instance a wrapper script `incus copy`s per Claude session,
// then deletes when the session ends -- one checkout sandbox per session
// without hand-managing a growing pool of long-lived containers, and without
// the shared-checkout collisions this session hit repeatedly.
sandboxTemplate: #Instance & {
	name: site.sandbox.instance + "-template"
	config: {
		"limits.cpu":     "\(site.sandbox.cpus)"
		"limits.memory":  "\(site.sandbox.memoryMiB)MiB"
		"boot.autostart": "false"
	}
	devices: {
		root: {type: "disk", path: "/", pool: site.pool, size: "\(site.sandbox.diskGiB)GiB"}
		eth0: #RestrictedNIC
	}
}

#Instance: {
	name:      #Name
	type:      "container"
	ephemeral: false
	profiles:  []
	source: {type: "image", alias: "alpine/edge"}
	config: {
		"security.privileged":     "false"
		"security.nesting":        "false"
		"security.idmap.isolated": "true"
		...
	}
	devices: {...}
}

#RestrictedNIC: {
	type:    "nic"
	name:    "eth0"
	network: site.network
	"security.acls":                       site.networkACL
	"security.acls.default.ingress.action": "reject"
	"security.acls.default.egress.action":  "allow"
	"security.ipv4_filtering":              "true"
	"security.ipv6_filtering":              "true"
	...
}

plan: {
	version: "forge-plan/v2"
	host:    site.host
	project: incusProject
	acl:     networkACL
	instances: [fossilInstance, sandboxTemplate]
	applySequence: [
		"incus project create \(site.project)",
		"incus project set \(site.project) <each config key from incusProject.config, one per call>",
		"incus network acl create \(site.networkACL) --project \(site.project)",
		"incus network acl edit \(site.networkACL) --project \(site.project)  # apply the ingress rule from `acl` above",
		"incus launch images:alpine/edge \(site.fossil.instance) --project \(site.project) -c limits.cpu=\(site.fossil.cpus) -c limits.memory=\(site.fossil.memoryMiB)MiB",
		"incus config device add \(site.fossil.instance) root disk path=/ pool=\(site.pool) size=\(site.fossil.diskGiB)GiB --project \(site.project)",
		"incus config device set \(site.fossil.instance) eth0 ipv4.address=\(site.fossil.address) security.acls=\(site.networkACL) --project \(site.project)  # confirm address is free first: incus network list-leases \(site.network)",
		"# inside fossilInstance: apk add fossil; fossil server /srv/files.fossil --port \(site.fossil.port) --localhost &",
		"tailscale serve --bg --tcp=\(site.fossil.port) tcp://\(site.fossil.address):\(site.fossil.port)  # run on bak itself; tailnet-only, no funnel, no public exposure",
		"incus launch images:alpine/edge \(site.sandbox.instance)-template --project \(site.project)  # stopped, used only as a copy source",
		"# per-session: incus copy \(site.sandbox.instance)-template <session-name> --project \(site.project) && incus start <session-name>",
		"# session end: incus delete --force <session-name> --project \(site.project)",
	]
	certificate: {
		name:         "claude-forge"
		restrictedTo: [site.project]
		precedent:    "matches the existing 'claude-code' cert already scoped to 'mailstack lane only'"
	}
	sizing: {
		reasoning: "This laptop's ~/.files checkout is 676.6MiB and the Fossil repo file itself is 561.9MiB; the household doesn't build Rust (no large incremental-compile/target-dir workload), so a sandbox only needs room for one checkout plus light Python/shell build artifacts, not gigabytes of toolchain cache. \(site.fossil.diskGiB)GiB on the fossil server is >7x the current repo size for growth (commits, checked-in generated artwork). \(site.sandbox.diskGiB)GiB per sandbox is >2x a bare checkout. \(site.sandbox.maxConcurrent) concurrent sandboxes at \(site.sandbox.memoryMiB)MiB plus the fossil server's \(site.fossil.memoryMiB)MiB stays well under bak's 11.4GiB RAM alongside its other 16 projects. Total project quota \(site.diskQuotaGiB)GiB covers the fossil server, the stopped template, and every concurrent sandbox at once, with headroom for image layers."
	}
	requires: [
		"Jack's explicit go-ahead before any command in applySequence runs against bak",
		"Confirm site.fossil.address is actually free on the sandbox0 bridge before applying (incus network list-leases sandbox0)",
		"fossil is not installed on bak yet (apk has fossil-2.28); needs `apk add fossil` inside fossilInstance, not on the bak host itself",
	]
}
