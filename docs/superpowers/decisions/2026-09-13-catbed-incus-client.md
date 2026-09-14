# Catbed administers bak with the Incus client

Jack requested the Incus client on catbed, connected to bak with broad
permissions. Install Alpine's `incus-client=7.0.1-r1` and grant its own TLS
certificate unrestricted Incus administration. This covers every project,
instance, profile, network, storage pool and trust entry exposed by bak's API.

The normal user `jack` runs the client. The default remote is `bak`, at
`https://bak.bishop-bearded.ts.net:8443`, with `default` as its initial project.
The name resolves to bak's Tailscale address `100.104.232.33`. Bak already had
its HTTPS listener; setup did not change listeners or firewall rules.

## Identity and server verification

Generate a new client certificate on catbed with
`incus remote generate-certificate`. Keep `~/.config/incus/client.key` on
catbed with mode 0600 and the containing directory at 0700. Only the public
`client.crt` crosses the established Tailscale SSH connection to bak:

```sh
ssh bak 'incus config trust add-certificate /dev/stdin --name catbed-jack --restricted=false --description "Jack on catbed: full Incus administration over Tailscale"' < ~/.config/incus/client.crt
```

This trust entry has `restricted: false` and no project allowlist. Existing
restricted certificates keep their existing scopes. No trust token, password,
or private key belongs in the checkout or package archive.

Copy bak's public `/var/lib/incus/server.crt` over the established SSH
connection into `~/.config/incus/servercerts/bak.crt` before adding the remote.
The pinned SHA-256 fingerprint is
`99836a113633c97272be9031d9ee405f78cc959a072df2edfa7d2641eba7ed8e`.
Then configure the remote without bypassing certificate verification:

```sh
incus remote add bak https://bak.bishop-bearded.ts.net:8443 --auth-type=tls --project default
incus remote switch bak
```

## Everyday use

```sh
incus list --all-projects
incus project list
incus list --project forge
incus exec INSTANCE --project PROJECT -- sh
incus project switch PROJECT
```

These run on bak because it is the default remote. Use `bak:` explicitly in
commands when desired, such as `incus list bak: --all-projects`. Catbed needs
Tailscale connectivity; the Incus connection itself uses mutual TLS over HTTPS
and does not require an SSH tunnel.

## Validation and recovery

Live evidence is recorded in
`alpine/verification/incus-bak/connection-verification.json`: authenticated API
access, unrestricted trust, visibility across projects and instances, and
creation followed by deletion of an otherwise unused temporary project.
Existing instances are not restarted for this check.

The package addition preserves every pre-existing installed package identity.
Alpine's client package also depends on LXC and dnsmasq; their services stay
disabled. No local Incus daemon is installed. The package archive retains 100
exact signed APKs in the scoped supplement
`alpine/packages/locks/c0155382d40b84878872.json`: the client's runtime closure,
all newly installed packages and their dependencies. The full workstation's
`current-lock` is unchanged; pre-existing archive gaps and package drift are
recorded separately in `alpine/verification/incus-bak/package-verification.json`.
Use the supplement's recovery instructions in `alpine/packages/incus-client/README.md`.

To revoke this client, use an independent administrative connection to bak:

```sh
ssh bak 'incus config trust remove 9c56d1c7517953a6846ab9f36fcb45b8fa6a816a70065c560c1f569012cd137c'
```

Then remove the remote locally with `incus remote switch local` followed by
`incus remote remove bak`. If catbed's private key is lost, generate a new
certificate, register that new public certificate through SSH, and remove the
old trust entry. Restoring packages does not restore the private client key.

References: [Incus authentication](https://linuxcontainers.org/incus/docs/main/authentication/),
[authorization](https://linuxcontainers.org/incus/docs/main/authorization/),
and [remote setup](https://linuxcontainers.org/incus/docs/main/reference/manpages/incus/remote/add/).
