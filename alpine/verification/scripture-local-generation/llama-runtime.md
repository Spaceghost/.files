# Private llama.cpp diagnostic runtime

The retained Qwen2.5 1.5B weights produced `OK` through native llama.cpp in
65.526 seconds with four workers. The subsequent comparison completed in
37.356 seconds with one worker and polling disabled. Both exited 0; see
[baseline](llama-basic.json) and [one-worker comparison](llama-singlethread.json).
These are short diagnostic results under the observed desktop load, not a
throughput guarantee or completed Scripture study. Both record
`study_saved: false`; production study generation and history integration were
not changed by these probes. The earlier path-error files retain a mistyped
model filename; the successful invocations contain the correct manifest digest.

Five signed Alpine x86_64 APKs form the additional private runtime:

| APK | Download bytes | Installed bytes |
| --- | ---: | ---: |
| llama-completion-0.4.0-r0 | 3,130 | 14,080 |
| llama.cpp-0.4.0-r0 | 2,317,730 | 6,054,302 |
| llama.cpp-libs-0.4.0-r0 | 4,245,654 | 11,169,912 |
| libggml-0.23.0-r0 | 486,484 | 1,164,406 |
| libggml-cpu-0.23.0-r0 | 6,040,356 | 14,561,384 |
| Total | 13,093,354 | 32,964,084 |

[Download records](llama-runtime-download.json) retain exact HTTPS URLs,
SHA-256 hashes and successful `apk verify` results using the existing Alpine
signing keys. [Inventory](llama-runtime-inventory.json) retains package metadata,
paths and symlink targets. [Archive records](llama-runtime-archive.json) identify
all five local Fossil unversioned artifacts and confirm restored hashes and
signatures. No global APK installation, new model download or publishing was
performed for this differential runtime.

The host already supplied musl 1.2.6-r3; libgcc, libstdc++, libgomp, libgfortran
and libquadmath 15.2.0-r9; libcrypto3 and libssl3 3.5.8-r0; openblas 0.3.30-r2;
and busybox-binsh 1.38.0-r4. These remain host dependencies, not additional
bundled APKs. The main `llama.cpp` APK supplies
`usr/lib/libllama-completion-impl.so`. The separate `libggml-cpu` APK supplies
the CPU kernels, including `libggml-cpu-haswell.so`; its `install_if` dependency
must be accounted for when extracting manually.

The tested layout is
`~/.local/share/oldbook/llama.cpp/runtime-0.4.0-r0/`, with the executable at
`usr/bin/llama-completion`. Set `LD_LIBRARY_PATH` to its `usr/lib` and
`usr/lib/llama.cpp`, and use its `usr/lib` as the working directory. GGML searches
the compiled `/usr/lib`, executable directory and current directory for CPU
backends. `GGML_BACKEND_PATH` accepts a library filename, not a directory.
Keep Ollama's different GGML libraries out of this loader path.
[Exact GGML loader source](https://github.com/ggml-org/ggml/blob/v0.23.0/src/ggml-backend-reg.cpp).

The existing model is
`~/.local/share/oldbook/ollama/models/blobs/sha256-183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4`.
Its 986,048,512-byte GGUF v3 file is passed directly with `-m`; no rename or
conversion is required. [Model manifest](model-manifest.json),
[model metadata](model.json) and [Apache 2.0 model license](MODEL-LICENSE.txt)
retain provenance for the already verified weights. llama.cpp and GGML use MIT;
their bundled notices remain in the archived APKs at
`usr/share/licenses/llama.cpp/LICENSE` and `usr/share/licenses/libggml/LICENSE`.

To restore the exact APKs locally, run this from the checkout. It creates a fresh
replay directory, verifies every archive hash and signature, and extracts files
without running APK install scripts:

```sh
python3 - <<'PY'
import hashlib, json, subprocess, tempfile
from pathlib import Path

evidence = Path('alpine/verification/scripture-local-generation')
runtime = Path.home() / '.local/share/oldbook/llama.cpp/replay-0.4.0-r0'
runtime.mkdir(parents=True, exist_ok=False)
with tempfile.TemporaryDirectory(prefix='oldbook-llama-apks-') as directory:
    for item in json.loads((evidence / 'llama-runtime-archive.json').read_text())['artifacts']:
        package = Path(directory) / Path(item['artifact']).name
        with package.open('wb') as output:
            subprocess.run(['fossil', 'uv', 'cat', item['artifact']], stdout=output, check=True)
        assert hashlib.sha256(package.read_bytes()).hexdigest() == item['sha256']
        subprocess.run(['apk', 'verify', str(package)], check=True)
        subprocess.run(['tar', '-xzf', str(package), '-C', str(runtime)], check=True)
PY
```

For an inference replay, use the exact command and environment recorded in
[llama-basic-invocation.json](llama-basic-invocation.json) or
[llama-singlethread-invocation.json](llama-singlethread-invocation.json), replacing
only the runtime prefix with the fresh replay path. Both use the retained model,
`--offline`, GPU layers 0, a 4096-token context, eight output tokens and a
120-second outer limit. The second uses `-t 1 -tb 1 --poll 0 --poll-batch 0`
and sets both `OPENBLAS_NUM_THREADS` and `OMP_NUM_THREADS` to 1. Preserve the
private profile HOME, working directory and library path from the selected
invocation. This document was prepared from retained evidence; no inference was
rerun to write it.
