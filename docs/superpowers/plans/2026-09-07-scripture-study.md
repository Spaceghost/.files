# Scripture study implementation plan

> **For agentic workers:** Execute these tasks with independent storage,
> generation, and reader ownership; use the current Superpowers TDD and
> verification-before-completion skills.

**Goal:** Restore the earlier reflections and build a source-backed local-AI
study library whose contents survive Fossil publication and rebuilds.

**Architecture:** Immutable per-entry JSON and the existing legacy catalog
are canonical. A transactionally refreshed SQLite serves readers. The local
Ollama writer saves and stages only its generated record.

**Tech Stack:** Python standard library, SQLite, Fossil, GTK 3, Conky, Ollama.

**Spec:** `docs/superpowers/specs/2026-09-07-scripture-study-design.md`.

## Global constraints

- Work on `alpine-oldbook`; preserve unrelated pending changes.
- Only local AI generates new Scripture study prose.
- Preserve the 33 original reflections, Bible-only Super+/, all-text ordering,
  fixed card geometry, immediate selected-card refresh, and slow background refresh.
- Keep personal journal and runtime SQLite files outside the checkout.
- No automatic provider fallback, model downloads, commits, or publication in
  the new generation command; exact new artifact staging reports commit needed.

## Task 1: Store and canonical records

Files: new `alpine/desktop/.local/lib/mbp_intel/scripture_study.py` and
`alpine/tests/test_scripture_study.py`.

Interfaces: `load_entries(assets, database=None)` returns dictionaries retaining
legacy fields plus `kind`; `save_entry(assets, entry, database=None, track=True)`
returns the saved artifact Path. Generated kinds are `study-note`,
`inspiration`, and `observation`. Fields and provenance follow the design.

- [x] Write and run failing tests for durable save/rebuild and corrupt input.
  A deleted SQLite must rebuild the same IDs; a changed canonical artifact must
  update the row; a deleted artifact must remove the row; corrupt artifacts
  must leave the previous database contents intact.
- [x] Implement validation, hash invalidation, transaction, private database
  creation, immutable atomic record save, and exact-path Fossil staging.
- [x] Run `python3 -m unittest discover -s alpine/tests -p 'test_scripture_study.py' -v`.

## Task 2: Local generator and full reader

Files: new `scripture_generation.py`, `mbp-intel-scripture-study`, and
`alpine/tests/test_scripture_generation.py`; verified source packs if available.

- [x] Write failing tests using a disposable local HTTP server for valid
  structured response, unknown citation, cloud model, and request failure.
- [x] Implement endpoint/model checks, source context and hashes, schema-bound
  generation, provenance, and validation before `save_entry`.
- [x] Provide list/show/rebuild/generate commands with explicit assets/database
  overrides for isolated verification. Show full prose and citations.
- [x] Run `python3 -m unittest discover -s alpine/tests -p 'test_scripture_generation.py' -v`.

## Task 3: Scripture integration

Files: `mbp-intel-scripture`, `mbp-intel-scripture-bar`,
`alpine/tests/test_scripture_selection.py`, and focused picker tests.

- [x] Write failing tests showing a selected study renders its body and that
  importing a legacy selection resolves current canonical content.
- [x] Load reflections and studies through the SQLite store; provide a dedicated
  picker. Preserve Bible-only find and all-collection ordering.
- [x] Dispatch right-click to the dedicated picker and left-click/SIGUSR1 to
  Bible search. Cover that dispatch with a pure helper and behavior tests.
- [x] Run `python3 -m unittest discover -s alpine/tests -p 'test_scripture*.py' -v`.

## Task 4: Deployment, transfer, evidence

- [x] Exercise actual local Fossil commits and transfer/rebuild in disposable
  repositories, including independent additions retained on merge.
- [x] Deploy new exact HOME-relative paths into a disposable preview, then live.
- [ ] Back up the existing Scripture selection, select the daily reflection,
  refresh only its panel, and preserve a screenshot of the restored content.
- [x] Run the Scripture and Conky policy suites and deployment recovery suite.
- [ ] Generate real new material only after local endpoint access is confirmed.
  Record any remaining blocker in `alpine/PROGRESS.md`.
- [ ] Review exact changes, document usage/recovery, and commit the task paths.
