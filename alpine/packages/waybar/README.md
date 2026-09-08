# Waybar Sway IPC recovery package

This package preserves Alpine edge's Waybar 0.15.0 feature set and adds recovery
when Sway closes an event subscription. The stock module otherwise retains its
last workspace tree while its worker repeatedly reads the disconnected socket.

The patch is an adaptation of upstream commit `b0b46ec039199d99c36a0d6637e13e292d66fbdc`
for the 0.15.0 IPC implementation. It reconnects with bounded backoff, replays
both workspace subscriptions, and requests a fresh tree after reconnection.

Build in a disposable root with the pinned source archive:

```sh
alpine/packages/waybar/build-offline \
    --source ~/.local/state/mbp-intel/sources/Waybar-0.15.0.tar.gz \
    --work /tmp/mbp-intel-waybar-build
```

`rootbld` obtains build dependencies in its disposable APK root. It does not add
development packages to the live host. The build retains Alpine's main,
community, and explicitly tagged testing repositories over HTTPS. Review the
APK and native recovery evidence before replacing the installed `0.15.0-r3`.
