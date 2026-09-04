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

The catalog and bookmarks were originally created from notes gathered by Brother Jaco van der Merwe.

Brother Jaco served faithfully for many years in mission work in Namibia and was part of the True Christian Church Brotherhood. Several years ago, he passed on to glory, leaving behind a testimony of faithful service and a sincere desire to point people to the Word of God.

The material that eventually became the catalog began very simply. Brother Jaco regularly spoke with people he met in the course of everyday life and mission work. Because of his beard and his manner of dress, people would sometimes make remarks or ask him questions. He saw these encounters as opportunities to speak with them about the Lord and the Scriptures.

As conversations developed, people would often ask questions about particular Bible subjects, Christian practices, or matters of faith. Brother Jaco began collecting Bible verses on his phone according to the different topics people asked him about. His purpose was not merely to give his own opinion, but to be able to turn directly to the Scriptures and show people what the Bible had to say.

Over time, this collection grew. It became, in a very practical sense, the working notes of an evangelist—Bible passages gathered through real conversations with people on the street and through the questions they sincerely wanted answered. As different subjects arose, Brother Jaco collected the verses that the Lord brought to his attention so that he could give people an answer from the Word of God.

This was especially important to him because he did not want people simply to dismiss what he said as his personal belief or opinion. Instead, he wanted them to be able to read the verses for themselves and see that the answers being given were grounded in Scripture.

One day, Brother Jaco's son (Llewellyn van der Merwe) saw the collection of topics and Bible references on his father's phone. Recognizing the usefulness of what had been gathered, he asked whether Brother Jaco would be willing to contribute those notes. From that simple beginning, the catalog was started.

The catalog of bookmakrs grew out of years of personal evangelism, conversations, questions, and opportunities to share the Gospel. Its topics reflect the kinds of questions ordinary people asked, and its verse references reflect Brother Jaco's desire to direct those people away from human opinion and toward the authority of the Bible.

The bookmarks and catalog remain a testimony to that purpose: to provide a practical Bible-help tool through which a person can quickly find Scriptures related to a particular subject and use the Word of God to answer sincere questions.

They are, in many ways, the collected notes of an evangelist—formed through years of meeting people, listening to their questions, and searching the Scriptures for answers that could be shared with them. Brother Jaco's desire was that people would not simply hear what a man thought, but that they would be shown what the Bible says and be encouraged to search the Scriptures for themselves.

Today this catalog of bookmarks are expanded by his children and grand children.

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
| `GETBIBLE_SSH_KEY`, `GETBIBLE_SSH_PUB` | Deploy key with write access on `getbible/bookmarks`; the private key must have no passphrase |
| `GETBIBLE_GIT_USER`, `GETBIBLE_GIT_EMAIL` | Author and committer of the downstream commit |
| `GETBIBLE_BOOKMARKS_REPO` (optional) | Downstream repository, default `git@github.com:getbible/bookmarks.git` |
| `GETBIBLE_BOOKMARKS_BRANCH` (optional) | Downstream branch, default `main` |

Example values, what each one must contain and the troubleshooting table are
in [docs/PUBLISHING.md](docs/PUBLISHING.md).

## Provenance

The catalogue as first committed here was imported from the getBible robot's
reviewed global bookmark sources: 61 topics, 2,155 verse links and 53 locales
of translated names, with ids, colours and coordinates unchanged. The robot
also carries sixteen locales it fills from another language's catalogue (its
interface fallback policy, for example Cherokee shown in English); those are
not translations, and fifteen of them were not imported. The sixteenth,
`ppk`, is the language code for Uma, under which the robot filed its
Indonesian catalogue; it is published under `id`. The import is reproducible
with `scripts/import_from_robot.py`.

## License

Apache License 2.0, see [LICENSE](LICENSE). The verse references are
translation independent and carry no Scripture text.
