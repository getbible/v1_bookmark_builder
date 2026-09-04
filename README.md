# getBible Bookmarks Builder (v1)

[![Build](https://github.com/getbible/v1_bookmark_builder/actions/workflows/build.yml/badge.svg)](https://github.com/getbible/v1_bookmark_builder/actions/workflows/build.yml)
[![Tests](https://github.com/getbible/v1_bookmark_builder/actions/workflows/ci.yml/badge.svg)](https://github.com/getbible/v1_bookmark_builder/actions/workflows/ci.yml)

This repository is the custodian of the getBible topic bookmarks: a reviewed
catalogue of topics, each with a colour, translated names and the Bible
verses that speak to it. The sources live in `data/` as plain JSON files.
The builder in `src/` validates them and renders the static JSON API that is
published to [`getbible/bookmarks`](https://github.com/getbible/bookmarks)
and served from there as files, the same way the other getBible API
repositories work.

There is no runtime and no server of its own. GitHub is the editing surface:
a person opens a pull request, or an application such as the getBible robot
or the getBible app writes a file through the GitHub API. Every push to the
default branch rebuilds the API and updates the downstream repository when
the content changed.

## In memory of Brother Jaco van der Merwe

The catalogue began as the personal bookmarks of Brother Jaco van der Merwe,
the first contributor to this project. Brother Jaco served for many years in
mission work in Namibia and was part of the True Christian Church
brotherhood. He passed on to glory several years ago. The topics and verse
links he gathered over a lifetime of study form the foundation of this
repository, and everything added since is built on his work.

## How it fits together

```text
data/topics.json, data/links/*.json, data/locales/*.json
  -> python3 src/builder.py validate         rules in docs/DATA.md
  -> python3 src/builder.py build            deterministic v1/ tree
  -> run.sh                                  commit and push v1/ to getbible/bookmarks
  -> a static file server                    serves the files
```

| Path | Purpose |
|---|---|
| `data/topics.json` | Topic ids, English names, colours, aliases, default flag |
| `data/links/<topic>.json` | Verse links of one topic as `[book, chapter, verse]` triples |
| `data/locales/<locale>.json` | Translated topic names for one locale |
| `src/` | The builder: flat Python modules run as scripts, standard library only |
| `run.sh` | Renders into a checkout of the downstream repository and commits the result |
| `.github/workflows/build.yml` | Publishes on every push to the default branch |
| `.github/workflows/ci.yml` | Lint, strict typing, tests, validation, publication dry run |
| `schema/` | JSON Schemas for every source and generated document |
| `scripts/` | The check runner and the one-off import from `getbible/robot` |
| `docs/` | The documentation listed below |

## Documentation

| Document | Read it when you want to |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Understand the two repositories, the modules in `src/`, determinism, versioning and checksums, and why deletion is final |
| [docs/DATA.md](docs/DATA.md) | Edit the sources: every file format, every validation rule, the operations table, the rule summary for validators, robot bundles |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | Contribute as a person (branch and pull request) or integrate an application (direct writes and pull requests through the GitHub API, with worked examples) |
| [docs/PUBLISHING.md](docs/PUBLISHING.md) | Set up or debug publication: every secret and environment variable with example values and defaults, what `run.sh` does, troubleshooting |
| [docs/CLI.md](docs/CLI.md) | Use the command line: `validate`, `normalize`, `build`, `import-bundle` |

The structure of the published files is described in the README of
`getbible/bookmarks`, next to the files themselves.

## Quick start

Python 3.12 or newer and git; the builder itself uses nothing outside the
standard library.

```bash
git clone https://github.com/getbible/v1_bookmark_builder.git
cd v1_bookmark_builder
python3 src/builder.py validate            # OK: 61 topics, 2155 verse links, 53 locales.
python3 src/builder.py build --output v1   # renders 1,376 files; v1/ is ignored by git here
```

To run everything CI runs:

```bash
python3 -m pip install -r requirements-dev.txt
bash scripts/run-checks.sh
```

## Growing the catalogue

Every change is a change to files under `data/`, reviewed and recorded by
git. Add a topic, add or remove verses, rename with the old wording kept as
an alias, translate names, or delete a topic outright: deleting removes it
from every published document at the next build, and git history is the
only memory of it. The operations table in [docs/DATA.md](docs/DATA.md#operations)
lists which files each change touches; [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)
shows the git flow and the GitHub API flow step by step, including how to
make a multi-file change one commit.

## Publication

`build.yml` runs on every push to `main` (or `master`). It configures the
getBible git identity with [`octoleo/git-user`](https://github.com/octoleo/git-user),
clones `getbible/bookmarks`, renders `v1/` in place and pushes a commit only
when the rendered files differ from what is already published. The
catalogue version in `index.json` increments automatically whenever the
content checksum changes.

The workflow needs the shared getBible secrets on this repository:

| Secret | Purpose |
|---|---|
| `GETBIBLE_GPG_KEY`, `GETBIBLE_GPG_USER` | Sign the downstream commit |
| `GETBIBLE_SSH_KEY`, `GETBIBLE_SSH_PUB` | Deploy key with write access on `getbible/bookmarks` |
| `GETBIBLE_GIT_USER`, `GETBIBLE_GIT_EMAIL` | Author and committer of the downstream commit |
| `GETBIBLE_BOOKMARKS_REPO` (optional) | Downstream repository, default `git@github.com:getbible/bookmarks.git` |
| `GETBIBLE_BOOKMARKS_BRANCH` (optional) | Downstream branch, default `main` |

Example values, what each one must contain and the troubleshooting table are
in [docs/PUBLISHING.md](docs/PUBLISHING.md).

## Provenance

Beyond Brother Jaco's bookmarks, the catalogue as first committed here was
imported from the getBible robot's reviewed global bookmark sources: 61
topics, 2,155 verse links and 53 locales of translated names, with ids,
colours and coordinates unchanged. The robot also carries sixteen locales it
fills from another language's catalogue (its interface fallback policy, for
example Cherokee shown in English); those are not translations and were not
imported. Its Indonesian catalogue, filed there under the regional tag `ppk`,
is published under `id`. The import is reproducible with
`scripts/import_from_robot.py`.

## License

Apache License 2.0, see [LICENSE](LICENSE). The verse references are
translation independent and carry no Scripture text.
