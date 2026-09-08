# CS4208 speakers with a false headphone-jack indication

The MacBookPro11,5 reports ALSA `Headphone Jack = 1` with an empty
socket. The user confirmed that explicit Pithos links produce audible speaker
output. The stock ACP speaker path interprets the jack state as unavailable;
WirePlumber consequently declines to select or link the speaker sink.

Use a card-specific WirePlumber profile override, with an included distribution
profile set and custom analog stereo speaker/headphone paths. Both paths include
the distribution mixer controls and override only Headphone jack availability to
unknown in both states. This preserves speaker/bass controls, volume mapping,
headphone muting, microphone inputs and the other distribution profiles. The
higher-priority speaker route is selectable again. Headphones remain manually
selectable in pavucontrol; automatic jack switching is intentionally unavailable
while the sensor is unreliable. This is a persistent software workaround, not a
repair of the sensor or proof of the underlying hardware/driver cause.

The rule matches the internal PCH card at PCI 00:1b.0. Configuration lives under
`alpine/desktop/.config/{wireplumber,alsa-card-profile}` and is deployed as user
configuration symlinks. It does not modify package-owned files or kernel modules.
The upstream profile/path includes allow distribution mixer improvements to apply.

## Validation

- Reproduced the original unavailable speaker route and missing default sink.
- Loaded the configuration with the installed WirePlumber 0.5.17 / PipeWire 1.6.8.
- Confirmed both custom ports are selectable; returned to Speakers.
- Restarted WirePlumber again and verified Speakers are the default output.
- Played a fresh three-second silent stereo WAV through the default output:
  sink RUNNING, unmuted, active speaker route and successful playback exit.
  No manual pw-link commands were used after installing the override.
- User confirmed audible music with the same underlying speaker mixer before
  installing this override. Audible confirmation after the override, a full reboot
  and physical headphone playback remain untested.
- Local runtime evidence: `~/.local/state/oldbook/audio-repair/permanent-*`.

## Recovery

Remove the deployed `~/.config/wireplumber/wireplumber.conf.d/51-oldbook-audio.conf`
symlink and restart WirePlumber through the existing session service owner. The
stock profile will return; the three unused ACP files may also be removed.
The original route state is saved in the local audio-repair directory. Re-enable
the rule to restore this workaround. No package installation was required.

## References

- https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/alsa.html
- https://github.com/PipeWire/pipewire/blob/master/spa/plugins/alsa/acp/compat.c
- https://github.com/PipeWire/pipewire/blob/master/spa/plugins/alsa/acp/alsa-mixer.c
