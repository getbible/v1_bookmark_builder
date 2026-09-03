# Publication

The builder never serves anything. It renders the API tree and commits it to
the downstream repository `getbible/bookmarks`, whose `v1/` directory is
served as static files. This mirrors the other getBible builders: the builder
repository owns the sources and the logic, the API repository owns nothing but
files.

## What `run.sh` does

```bash
./run.sh [--repo=URL] [--branch=NAME] [--target=DIR] [--pull] [--push] [--dry-run]
```

1. Validates `data/` and stops on any rule violation.
2. Clones the downstream repository into `--target` (default `./bookmarks`
   next to the caller, ignored by git) or, with `--pull`, resets an existing
   checkout to the remote branch, discarding whatever a previous dry run left
   behind.
3. Renders `v1/` in place. The builder reads the previously published
   `v1/index.json` to learn the last catalogue version and checksum. A
   missing `index.json` starts at version 1; a present but damaged one stops
   the build, because the version must never move backwards.
4. Stages `v1/`. When nothing changed it stops with "Nothing to commit".
5. Commits `Update bookmarks API to catalogue version N` and, with `--push`,
   pushes to the downstream branch.

Only `v1/` is touched. The downstream README and license are never rewritten.

Try it locally against a throwaway repository:

```bash
git init --initial-branch=main /tmp/downstream
git -C /tmp/downstream commit --allow-empty -m "Initial commit"
./run.sh --target=/tmp/downstream --dry-run
```

## Version and checksum

`v1/all.json` holds the complete content and nothing else: every topic with
its verses and every locale. Its SHA-256 is the catalogue `checksum` written
to `v1/index.json`. Before rendering, the builder compares the new checksum
with the published one:

| Situation | `catalog_version` |
|---|---|
| No published `index.json` | 1 |
| Same checksum | unchanged, and no commit is made |
| Different checksum | previous + 1 |
| `index.json` unreadable or invalid | the build fails |

Nobody maintains the number by hand, a rebuild without a data change is a
no-op, and any content change, including a translation, produces a new
version. `schema_version` is separate: it only changes when the shape of the
documents changes, and that is a deliberate code change in this repository.

## The workflow

`.github/workflows/build.yml` runs on every push to the default branch and on
manual dispatch, serialised so two publications never race:

1. Check out this repository and set up Python.
2. Configure the getBible git identity with `octoleo/git-user@v2`: GPG key for
   signed commits, SSH key for the push, name and email.
3. `./run.sh --pull --push`.

Secrets, all shared with the other getBible builders:

| Secret | Purpose |
|---|---|
| `GETBIBLE_GPG_KEY`, `GETBIBLE_GPG_USER` | Commit signing |
| `GETBIBLE_SSH_KEY`, `GETBIBLE_SSH_PUB` | Deploy key with write access to `getbible/bookmarks` |
| `GETBIBLE_GIT_USER`, `GETBIBLE_GIT_EMAIL` | Author and committer of the downstream commits |
| `GETBIBLE_BOOKMARKS_REPO` (optional) | Downstream repository URL, default `git@github.com:getbible/bookmarks.git` |
| `GETBIBLE_BOOKMARKS_BRANCH` (optional) | Downstream branch, default `main` |

A failed validation fails the workflow before anything is cloned, so a bad
edit is visible in the Actions tab and never reaches the API.

## Serving

Point a static file server at the downstream repository's `v1/` directory.
The documents are plain JSON with stable paths, so a plain nginx `root` with
`gzip` enabled and long cache headers is enough; the downstream README
describes every file. Updating the server is a `git pull` of the downstream
repository, on a timer or from a webhook.
