# Architecture

## Two repositories, one direction

| Repository | Role | What lives there |
|---|---|---|
| `getbible/v1_bookmark_builder` (this one) | Custodian and builder | The canonical sources under `data/`, the renderer under `src/`, tests, schemas, documentation, the publication workflow |
| `getbible/bookmarks` | Static API | `LICENSE`, a README describing the files, and the generated `v1/` tree. Nothing else, no runtime |

Data flows in one direction only. People and applications change files in
this repository; the builder renders them and commits the result downstream;
a web server publishes the downstream `v1/` directory as plain files. Nobody
edits the downstream repository by hand, and the builder never touches
anything there except `v1/`.

```text
             pull request            push to main
 person  ───────────────►  data/  ───────────────►  build.yml
 robot   ── contents API ►                            │ run.sh
 app     ── contents API ►                            ▼
                                            getbible/bookmarks: v1/  ───►  nginx
```

This is the same shape as the other getBible builders (`v2_builder`,
`v3_builder`): the builder owns logic and sources, the API repository owns
files, and `octoleo/git-user` gives the workflow the shared getBible git
identity for the downstream commit.

## Sources

`data/` holds three kinds of documents, one file per topic and per locale so
that independent edits touch independent files:

| File | Holds |
|---|---|
| `data/topics.json` | id, English name, colour, aliases and default flag of every topic |
| `data/links/<topic>.json` | the verses linked to one topic as `[book, chapter, verse]` triples |
| `data/locales/<locale>.json` | translated topic names for one locale |

The formats and every validation rule are in [DATA.md](DATA.md). The rules
are the same ones the getBible robot enforces in its moderation pipeline, so
a change accepted there is accepted here unchanged.

## The renderer

`src/` is a set of flat Python modules run as scripts, with no dependency
outside the standard library:

| Module | Responsibility |
|---|---|
| `src/builder.py` | Command line entry point: `validate`, `normalize`, `build`, `import-bundle` ([CLI.md](CLI.md)) |
| `src/catalog.py` | The in-memory catalogue, field validators and every mutation with its invariants |
| `src/sources.py` | Loading `data/` strictly and writing it back in canonical form |
| `src/render.py` | Rendering the `v1/` tree, the checksum and the catalogue version |
| `src/bundle.py` | Applying a robot contribution bundle to the catalogue |
| `src/jsonfmt.py` | The deterministic JSON writer used for sources and output |
| `src/canon.py` | The 66-book Protestant canon: chapter counts, coordinate bounds, book names |
| `src/meta.py` | The schema version and the builder version |

Everything is deterministic. The same `data/` always renders to the same
bytes: keys are written in a fixed order, verse triples on one line, lists
sorted, no timestamps. A rebuild without a data change produces no diff, so
the publication step can rely on `git status` to decide whether anything
happened.

## Versioning and checksums

The generated documents carry two version numbers and one checksum:

- `schema_version` describes the shape of the documents. It changes only when
  the renderer changes what it emits, which is a deliberate code change here.
- `catalog_version` counts published content changes. It lives only in
  `v1/index.json` and is not stored in the sources. Before rendering, the
  builder reads the previously published `index.json`: same checksum, same
  version; different checksum, version plus one; no file, version one. A file
  that exists but is unreadable or malformed stops the build, because the
  version must never move backwards.
- `checksum` is the SHA-256 of `v1/all.json`, the one document that holds the
  complete content (every topic with its verses, every locale). Any change to
  the content, including a translation, changes it. Consumers can verify a
  download by hashing that single file.

## Deletion is deletion

A topic removed from `data/topics.json` (with its links file deleted and its
translations dropped) disappears from every generated document at the next
build, and its id may be used again. There are no tombstones and no retired
list. The git history of this repository is the record of what existed.

## Verification

`scripts/run-checks.sh` runs what CI runs: ruff formatting and linting,
strict mypy, byte-compilation, `validate`, a build into a scratch directory
followed by `build --check` against it (proving determinism), and the unit
tests. The tests cover the validators, every mutation, source round trips,
schema conformance of every generated document, the version logic and the
command line. CI additionally performs a publication dry run of `run.sh`
against a throwaway git repository.
