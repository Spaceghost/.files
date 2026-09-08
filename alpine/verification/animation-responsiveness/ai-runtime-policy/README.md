# Alienware inference policy

The user explicitly prohibited running Ollama or model workers on this MacBook
Pro. The live Ollama server and worker were terminated and subsequent process
checks found neither running. The desktop launcher now requires an explicit
local opt-in before opening runtime state or starting a backend. Missing,
malformed and disabled policy refuse with an Alienware message.

The deployed `~/.config/oldbook/ollama.json` selects `alienware` and disables
local startup. No remote endpoint was guessed or configured, and this change
makes no claim that Alienware inference is connected. `--help` remains usable.
The launcher can still be used on an explicitly configured inference host;
there is no automatic fallback from Alienware to the MacBook.

All 6 public CLI policy tests and 10 existing fake-backend lifecycle tests pass.
The mapped feature batch passed 128/130 tests; two existing Conky click checks
failed (a 20-second selection timeout and an asynchronous advancement assertion).
They do not execute the changed launcher. The full failure log is retained.
`installed.json` records the deployed policy and a real refused invocation that
never starts inference. No personal history, model data or credentials are here.

Recovery is configuration-based on a machine intended for inference: require
both `local_server_enabled: true` and `inference_host: "local"`. Do not enable
that policy on the MacBook without a new explicit user instruction.
