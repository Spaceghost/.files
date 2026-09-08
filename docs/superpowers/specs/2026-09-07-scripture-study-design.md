# Scripture reflections and local study library

Restore the earlier Scripture reflection and practice display. The existing
33 entries in `alpine/assets/scripture/reflections.json` remain unchanged. A
saved plain passage currently hides that display; restore the daily reflection
after backing up the live selection. Keep explicit passage selection working.

## Reading and selection

The existing Scripture card retains its geometry and refresh interval. A
right-click on the search bar opens a dedicated reflections and study picker.
Left-click and Super+/ remain Bible-only. Super+Shift+/ retains Torah, Talmud,
reflections/studies, then Bible order. Choosing entries and click-to-advance
load the current record from SQLite. Concurrent reading-history work preserves
the content of prior selections as private snapshots; choosing a catalog entry
again uses its current content. Full entries and citations are readable through
`mbp-intel-scripture-study show ID`.

## Durable content

Fossil tracks the existing reflection catalog and immutable generated JSON
records under `alpine/assets/scripture/study/entries/`. Each new record has a
collision-resistant ID, kind, reference, title, context, body, practice,
source excerpts and their hashes, and local-model provenance. Saves add only
their exact record path to Fossil and report the pending commit. Normal
reviewed commits and the existing publication workflow carry this material.

SQLite at `$XDG_DATA_HOME/mbp-intel/scripture/study.sqlite3` (defaulting to
`~/.local/share`) is a materialized reading library. Hash the canonical source
bytes and rebuild transactionally when they change, including after pull and
update. Source validation must complete before replacing a good library.
The runtime database, journals, selection, and personal desktop journal stay
outside the checkout. An offline clone/update can reconstruct every entry.

Do not add tables to `files.fossil`: custom SQL rows are not versioned Fossil
artifacts and do not acquire push/pull behavior. Do not use the unversioned
area, whose overwrite semantics cannot merge additions and which is excluded
from this checkout's Git mirror.

References: [Fossil artifacts](https://fossil-scm.org/home/doc/trunk/www/fossil-is-not-relational.md),
[unversioned files](https://fossil-scm.org/home/doc/trunk/www/unvers.wiki).

## Generation

Only an explicitly configured local Ollama endpoint may generate new prose.
Support loopback, private LAN, and Tailscale addresses, disable proxies and
redirects, check installed model metadata for local weights, and reject cloud
models. No fallback provider and no automatic model downloads. The initial
Alienware endpoint is unavailable and its Tailscale SSH policy denies access;
new content generation remains pending until a local endpoint is available.

Use exact primary Scripture context from the bundled KJV, with attributed,
hashed source excerpts, and optional verified public-domain commentary packs.
Require structured output to cite only supplied source identifiers. Clearly
distinguish interpretation and practical inspiration from quoted Scripture;
do not invent historical context, quotations, or original-language claims.
Retain model name, digest, endpoint, creation time, and prompt digest. Reject
invalid or incomplete responses before saving any entry.

References: [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs),
[generation API](https://docs.ollama.com/api/generate),
[local-only mode](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features).

## Verification and recovery

Test durable saves, source changes/deletion, corrupt input, rebuild from an
empty data directory, and Fossil transfer between disposable local checkouts.
Test the model boundary with a local HTTP fixture, including cloud rejection
and invalid citations. Exercise picker scope, selection, rendering, and bar
button behavior. Retain native panel evidence and the prior selection backup.
Restore the selection backup and reverse the exact code/config deployment to
recover; canonical entries are preserved independently of the runtime SQLite.
