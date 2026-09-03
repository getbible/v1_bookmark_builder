# getBible Bookmarks Builder (v1)

[![Build](https://github.com/getbible/v1_bookmark_builder/actions/workflows/build.yml/badge.svg)](https://github.com/getbible/v1_bookmark_builder/actions/workflows/build.yml)
[![Tests](https://github.com/getbible/v1_bookmark_builder/actions/workflows/ci.yml/badge.svg)](https://github.com/getbible/v1_bookmark_builder/actions/workflows/ci.yml)

This repository is the custodian of the getBible topic bookmarks: a reviewed
catalogue of topics, each with a colour, translated names and a list of Bible
verses that speak to it. The canonical data lives in `data/` as plain JSON
files, and this builder renders it into the static JSON API that is published
to [`getbible/bookmarks`](https://github.com/getbible/bookmarks) and served
from there as files, exactly like the other getBible API repositories.

There is no runtime. GitHub is the editing surface: a person opens a pull
request, or an application such as the getBible robot or app writes a file
through the GitHub contents API. Every push to the default branch rebuilds the
API and updates the downstream repository when anything changed.

```text
data/topics.json, data/links/*.json, data/locales/*.json
  -> bookmark-builder validate                (rules in docs/DATA.md)
  -> bookmark-builder build --output v1       (deterministic JSON tree)
  -> run.sh: commit and push v1/ into getbible/bookmarks
  -> nginx serves the files
```

## Repository layout

| Path | Purpose |
|---|---|
| `data/topics.json` | Topic ids, English names, colours, aliases, default flag |
| `data/links/<topic>.json` | Verse links of one topic as `[book, chapter, verse]` triples |
| `data/locales/<locale>.json` | Translated topic names for one locale |
| `bookmark_builder/` | The Python package: validation, deterministic renderer, CLI |
| `schema/` | JSON Schemas for every source and generated document |
| `run.sh` | Builds into a checkout of the downstream repository and commits the result |
| `.github/workflows/build.yml` | Publishes on every push to the default branch |
| `.github/workflows/ci.yml` | Lint, strict typing, tests and a publication dry run |
| `scripts/` | Check runner and the one-off import from `getbible/robot` |
| `docs/` | [Data and editing contract](docs/DATA.md), [publication](docs/PUBLISHING.md) |

## Quick start

Python 3.12 or newer and git are the only requirements; the builder itself
uses nothing outside the standard library.

```bash
git clone https://github.com/getbible/v1_bookmark_builder.git
cd v1_bookmark_builder
python3 -m bookmark_builder validate
python3 -m bookmark_builder build --output v1
```

`build` writes the complete API tree (one file per topic, per book, per
canonical chapter and per locale, plus the discovery and all-in-one documents)
and prints the catalogue version and checksum. `v1/` is ignored by git here; it
only ever lives in the downstream repository.

`normalize` rewrites `data/` in the builder's canonical formatting after
hand or API edits. To run everything CI runs:

```bash
python3 -m pip install -r requirements-dev.txt
bash scripts/run-checks.sh
```

## Growing the catalogue

Every change is a change to one or more files under `data/`, reviewed and
recorded by git:

- **Add a topic**: append it to `data/topics.json` and create
  `data/links/<id>.json` with its verses.
- **Add or remove verses**: edit the topic's links file.
- **Translate a name**: edit `data/locales/<locale>.json`.
- **Delete a topic**: remove it from `data/topics.json`, delete its links file
  and drop its entry from every locale. Deleting is complete and final for the
  published API; git history is the only memory of it.

The exact file formats, the validation rules and worked examples for the
GitHub contents API (the route the robot and the app use) are in
[docs/DATA.md](docs/DATA.md). Contribution bundles exported by the robot's
moderation tooling can be applied locally with
`python3 -m bookmark_builder import-bundle <file>`.

## Publication

`build.yml` runs on every push to the default branch. It configures the
getBible git identity with
[`octoleo/git-user`](https://github.com/octoleo/git-user), clones
`getbible/bookmarks`, renders `v1/` in place and pushes a commit only when the
rendered files differ from what is already published. The catalogue version in
`index.json` increments automatically whenever the content checksum changes,
so nobody maintains a version number by hand. Details, the required secrets
and the local dry run are in [docs/PUBLISHING.md](docs/PUBLISHING.md).

## Provenance

The initial catalogue was imported from the getBible robot's reviewed global
bookmark sources: 61 topics, 2,155 verse links and 53 locales of translated
names, with ids, colours and coordinates unchanged. The robot also carries
sixteen locales that it fills from another language's catalogue (its UI
fallback policy, for example Cherokee shown in English or Modern Hebrew shown
in Ancient Hebrew); those are not translations and were not imported. The
robot's Indonesian catalogue, filed there under the regional tag `ppk`, is
published under `id`. The import is reproducible with
`scripts/import_from_robot.py`.

## License

Apache License 2.0, see [LICENSE](LICENSE). The verse references are
translation independent and carry no Scripture text.
