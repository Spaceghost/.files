# Local CPU Scripture generation

The configured Alienware host was offline during this run; its recorded local
API addresses and bounded Tailscale SSH probe were unavailable. The laptop had
no Ollama/llama executable, model directory or listener. No remote settings were
changed and no cloud inference provider was used.

The approved fallback retains a private Alpine CPU Ollama runtime and Qwen2.5
1.5B Q4_K_M weights. It fits the observed 16 GiB machine with ample available
memory and disk. No system package or boot service was installed.

- APK: `ollama-0.17.7-r1.apk`, MIT, verified with the existing Alpine signing keys
  before extraction/execution. SHA-256:
  `9209558ef09917961c0b3eb96724c5532cc734ff3df2cb669d24a8e86945aafb`.
- Exact APK is archived in Fossil's unversioned store at
  `sha256/9209558ef09917961c0b3eb96724c5532cc734ff3df2cb669d24a8e86945aafb/ollama-0.17.7-r1.apk`.
  It was restored and verified again. Alpine's compiled binary reports version
  `0.0.0`; the signed package metadata, source commit and hashes identify it.
- Model: `qwen2.5:1.5b`, Apache-2.0, 986061892 bytes. Manifest SHA-256:
  `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b`.
  All five config/weight/template/license layers were independently hashed and
  checked against `model-manifest.json`. Full model metadata and license are
  preserved beside this document.

Runtime: `~/.local/share/oldbook/ollama/runtime-0.17.7-r1/`.
Retained weights: `~/.local/share/oldbook/ollama/models/`.
Private logs/profile: `~/.local/state/oldbook/ollama/`.
The wrapper respects `XDG_DATA_HOME` and `XDG_STATE_HOME`.

Replay a generation using the retained files:

```sh
oldbook-scripture-local '2 Corinthians 12:9' --kind study-note
```

`oldbook-scripture-local` starts only its own loopback server on port 11435,
sets `OLLAMA_NO_CLOUD=1`, uses a 4096-token context and one request/model at a
time, and runs at lower scheduling priority. It delegates to the existing
`oldbook-scripture-study` CLI, which validates installed local weights and model
metadata before generation. The wrapper retains the weights and cleans up its
owned server after the request, including interruption. An unrelated listener
or another generation is left untouched. The older explicit endpoint/model CLI
still works for Alienware whenever that machine is available.

Local CPU generation has an explicit 900-second HTTP request timeout; the generic
endpoint CLI retains its 60-second default. Startup, metadata checks and cleanup
add overhead, so this is not a 900-second total CLI wall-time guarantee.
The optimized run still reached its
earlier 300-second bound while a read-only sample measured roughly 798 MHz under
load. The cause of that low CPU frequency was not established, and no power or
hardware settings were changed. `cpu-live-sample.json` records the measurement.

Reinstall the private runtime from the archive without altering APK world:

```sh
fossil uv cat sha256/9209558ef09917961c0b3eb96724c5532cc734ff3df2cb669d24a8e86945aafb/ollama-0.17.7-r1.apk > /tmp/ollama-0.17.7-r1.apk
apk verify /tmp/ollama-0.17.7-r1.apk
mkdir -p ~/.local/share/oldbook/ollama/runtime-0.17.7-r1
tar -xzf /tmp/ollama-0.17.7-r1.apk -C ~/.local/share/oldbook/ollama/runtime-0.17.7-r1
ln -s libggml-base.so ~/.local/share/oldbook/ollama/runtime-0.17.7-r1/usr/lib/ollama/libggml-base.so.0
```

Preserve the retained model directory in machine backups. If downloading the
public tag again, verify the manifest and every layer against the recorded
hashes; a tag alone does not establish exact model identity. Model weights and
the private Ollama profile are not committed to the repository.

The first actual request exposed a native grammar parser limit: the schema's
1200/2400-character string bounds expanded to unsupported repetition counts.
The request was cancelled without saving an entry. A failing fixture reproduced
that rejection. The final schema constrains JSON structure while the existing
application validator continues to enforce all title/body/practice limits and
known source citations; a separate regression rejects oversized generated text.

The signed APK itself omits the `libggml-base.so.0` alias needed by its optimized
CPU libraries. Before the private alias repair, `ldd` failed and the runtime
silently used generic CPU code; the first corrected request timed out. The alias
above fixes only the extracted runtime, preserving every signed binary/library
byte. `cpu-loader-repair.json` and the before/after loader logs record this cause
and repair. Replay includes the alias; the longer local wait is separately
justified by the subsequent optimized run and measured CPU frequency.
