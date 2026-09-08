# Reflections and study library

The Scripture card can display the original 33 reflections and new study notes,
inspirations, and observations. Right-click its search bar to choose one.
Left-click and Super+/ search Bible verses; Super+Shift+/ searches all texts.
Click the reading card to advance. To restore the daily reflection:

```sh
oldbook-scripture daily
```

Read the full library and complete entries, including source excerpts:

```sh
oldbook-scripture-study list
oldbook-scripture-study show jesus-compassion
oldbook-scripture-study rebuild
```

## SQLite and Fossil

The reading SQLite is `~/.local/share/oldbook/scripture/study.sqlite3`, or
`$XDG_DATA_HOME/oldbook/scripture/study.sqlite3`. It contains the complete
library. The unchanged `../reflections.json` and new `entries/*.json` files are
canonical and are tracked in Fossil. The reader checks source hashes and
refreshes SQLite when files change, including after pull and update.

Each new entry is an immutable file with a unique ID. Independent additions
on different machines merge as separate files. Deleting the runtime SQLite
loses no reading content: the next reader call reconstructs it. Selection and
the separate personal desktop journal are outside this versioned collection.

Generation stages only the exact new record and reports that a commit is
pending. Review and commit that record to include it in the existing branch
publication flow. New uncommitted records have not yet been published.
After receiving commits on another checkout, update it and rebuild/read:

```sh
fossil pull
fossil update alpine-oldbook
oldbook-scripture-study rebuild
```

Fossil repository SQL tables are not the file-versioning interface. Custom
tables inside `files.fossil` do not become synced study content. The separate
canonical records also avoid conflicting binary SQLite edits and survive the
repository's Git mirror. See [Fossil's artifact model](https://fossil-scm.org/home/doc/trunk/www/fossil-is-not-relational.md).

## Local generation and sources

Use an already installed model on a local Ollama server:

```sh
oldbook-scripture-study generate 'John 13:14' --kind inspiration \
    --endpoint http://127.0.0.1:11434 --model qwen3.5:27b-text
```

Kinds are `study-note`, `inspiration`, and `observation`. A private LAN or
Tailscale IP address can also be specified. The command rejects public endpoints
and cloud models, checks local model metadata, and has no fallback provider or
automatic model download. A failed request saves no generated entry. Ollama's
[local-only server setting](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features)
is `OLLAMA_NO_CLOUD=1`.

The model receives the exact full chapter around the selected bundled KJV
passage. This is primary Scripture context, not a substitute for an academic
commentary. The generation prompt restricts claims to supplied text and
distinguishes interpretation/application from quotation. Source excerpts,
title, reference URL, license, hashes, and the IDs actually cited are saved
with each entry. Model name, local model digest, endpoint, generation time,
and prompt hash are preserved as provenance. Unknown citations and invalid
or incomplete output are rejected. Read the full entry to review its reasoning
against its sources; automatic structural checks do not establish exegesis.

The original reflections retain their original wording and authorship status;
they are not relabeled as locally generated material.

For isolated trials, pass global `--assets` and `--database` paths pointing at
a disposable copy and use `generate --no-track`. This flag saves a canonical
entry without staging it; the disposable asset path provides the isolation.
A custom database path that belongs to another application is refused.
