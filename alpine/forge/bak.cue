package forge

// Right-sized against real numbers, not guesses: this laptop's ~/.files
// checkout is 676.6MiB and the Fossil repo file is 561.9MiB (`du -sh ~/.files`,
// `ls -lh ~/.local/share/fossil/files.fossil`, checked at plan time). No Rust
// toolchain workload here, so no need to provision for incremental-compile
// caches. See `plan.sizing.reasoning` in schema.cue for the full arithmetic.
site: {
	host:         "bak"
	project:      "forge"
	pool:         "bak" // existing ZFS pool, 913G used / 889G avail -- ample headroom
	network:      "sandbox0" // existing shared bridge already used by every codex-*/atlas-* project on bak
	networkACL:   "forge-fossil"
	diskQuotaGiB: 16
	fossil: {
		instance:       "forge-fossil"
		cpus:           1
		memoryMiB:      512
		diskGiB:        4
		port:           8080
		gatewayAddress: "172.30.240.1"
		// Provisional -- confirm free with `incus network list-leases sandbox0`
		// before applying. Chosen to sit clear of the one address already in
		// documented use on this bridge (172.30.240.226, bak-portal-desktop).
		address: "172.30.240.230"
	}
	sandbox: {
		instance:      "forge-sandbox"
		cpus:          2
		memoryMiB:     1536
		diskGiB:       2
		maxConcurrent: 3
	}
}

otherPools: ["personal", "romsort-build", "wd-backup"]
