# Offline reading texts

The bundled KJV contains 31,102 verses. `reflections.json` retains the 33 curated
reflections. `jewish-texts.jsonl.gz` adds English Torah and Babylonian Talmud:

- Torah: five books, 5,846 segments, *The Holy Scriptures: A New Translation*
  (Jewish Publication Society, 1917), public domain.
- Babylonian Talmud: 37 tractates, 81,481 segments, *William Davidson Edition —
  English*, the William Davidson digital edition of the Koren Noé Talmud,
  including commentary by Rabbi Adin Even-Israel Steinsaltz. Sefaria identifies
  this edition as CC-BY-NC; see the [edition credits and terms](https://www.sefaria.org/william-davidson-talmud)
  and [CC BY-NC 4.0 license](https://creativecommons.org/licenses/by-nc/4.0/).

The source is the official [Sefaria Export](https://github.com/Sefaria/Sefaria-Export).
`sefaria-sources.json` records each exact input URL and SHA-256.
`jewish-texts-manifest.json` records versions, licenses, segment counts and the
output hash. Conversion strips HTML markup and normalizes whitespace; it does
not retranslate the text. Each output segment keeps edition, license and source
URL. This local packaging implies no endorsement by the source publishers.
These are English texts; Hebrew/Aramaic and Jerusalem Talmud are not bundled.

## Reproduce without networking

`sefaria-inputs-archive.json` identifies the exact input bundle stored in the
local Fossil unversioned archive. Export its `artifact` with `fossil uv export`,
verify the listed SHA-256, and extract into a disposable directory. Then run:

```sh
alpine/bin/build-jewish-texts --inputs /tmp/sefaria-inputs \
  --sources alpine/assets/scripture/sefaria-sources.json \
  --output /tmp/jewish-texts-rebuild
cmp alpine/assets/scripture/jewish-texts.jsonl.gz \
  /tmp/jewish-texts-rebuild/jewish-texts.jsonl.gz
```

The builder validates all input hashes and writes deterministic gzip output.
The network-disabled rebuild matched the packaged output byte for byte.
