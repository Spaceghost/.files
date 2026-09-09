# Building packages away from the laptop

The MacBook is the desktop. A Waybar C++ compile pins both of its fans at
maximum for several minutes and makes the machine unpleasant to sit at, so
packages are built on `alienware` or `bak` and only the finished APK comes back.

## Why not a cross compiler

Both machines are x86_64. Building for the MacBook elsewhere is a *native*
build on faster hardware, not cross-compilation, so there is nothing for a
cross toolchain to do. `zig cc` is the wrong lever for a second reason as well:
`abuild` is a package build system rather than a compiler, and it needs a
complete musl sysroot with Alpine's `-dev` packages, patches and `pkg-config`
paths. A drop-in C compiler does not supply that; a rootless Alpine container
supplies exactly it, and runs the same `abuild` this checkout already uses.

## Using it

```sh
alpine/bin/remote-build hosts               # which build host answers
alpine/bin/remote-build list                # what this checkout can build
alpine/bin/remote-build build waybar        # build there, sign here
alpine/bin/remote-build build waybar --plan # print every command, connect to nothing
```

`build` tars `alpine/packages/<name>` to the host, runs the container recipe
printed by `--plan`, brings the APKs back, signs them with this machine's key,
checks them with `apk verify`, and files them in `~/.cache/oldbook-apks` under
the identity apk itself computes. `package-archive snapshot` then picks them up
in the usual way.

## The signing key stays here

The private key at `~/.config/abuild/jack-6a9e83bd.rsa` is never sent anywhere.
The build host generates a throwaway key for itself, and `remote-build` replaces
that signature on this machine.

That replacement is exact rather than approximate. An APK is three concatenated
gzip streams — signature, control, data — and an APK v2 signature is an RSA
signature over the SHA-1 of the **control segment alone**. The identity apk
publishes as `C:` is the SHA-1 of that same segment, so re-signing cannot change
which package a file is; signing the same package twice produces identical
bytes. One detail matters: apk reads the whole file as a single tar stream that
happens to be split across segments, so the signature segment must be written
*without* a tar end-of-archive marker. With one, apk never reaches the control
and data segments and rejects the package as "file format is invalid or
inconsistent" rather than as unsigned.

`remote-build sign <apk>` applies the same step by hand, which is how a package
built anywhere else is brought into the archive.

## Access

Reaching a build host is the only part that needs a person. The desktop keeps no
ssh key: remote agents use Tailscale SSH, so the far side must run
`sudo tailscale up --ssh` and the tailnet policy must permit `oldbook` to reach
it. As of 2026-09-08 neither host accepts a connection from `oldbook` —
`alienware` answers "tailnet policy does not permit you to SSH to this node" and
`bak` refuses publickey authentication — so `remote-build build` reports both
refusals and stops. It does not fall back to building here.

## The local guard

`alpine/bin/remote-build guard --install` writes a shim to `~/.local/bin/abuild`,
which precedes `/usr/bin` on `PATH`. It refuses to compile and names the remote
command instead. Set `OLDBOOK_ALLOW_LOCAL_BUILD=1` for a single deliberate local
build, or `guard --remove` to take the shim away.
