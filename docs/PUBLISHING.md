# Publication

The builder never serves anything. It renders the API tree and commits it to
the downstream repository `getbible/bookmarks`, whose `v1/` directory is
served as static files. Publication is automatic: every push to this
repository's default branch runs [`build.yml`](../.github/workflows/build.yml),
which runs `run.sh`.

## Secrets and environment variables

The workflow reads these repository secrets (Settings → Secrets and
variables → Actions). They are the same secrets the other getBible builders
use; if they exist as organisation secrets, grant this repository access to
them instead of creating new ones.

| Secret | Required | Used for | Example value |
|---|---|---|---|
| `GETBIBLE_GPG_KEY` | yes | Signing the downstream commit. The ASCII-armoured **private** GPG key | `-----BEGIN PGP PRIVATE KEY BLOCK-----` … `-----END PGP PRIVATE KEY BLOCK-----` |
| `GETBIBLE_GPG_USER` | yes | The identity of that key, as shown by `gpg --list-keys` | `getBible Builder <builder@getbible.net>` |
| `GETBIBLE_SSH_KEY` | yes | Cloning and pushing `getbible/bookmarks` over SSH. The **private** key of a deploy key that has write access on that repository | `-----BEGIN OPENSSH PRIVATE KEY-----` … `-----END OPENSSH PRIVATE KEY-----` |
| `GETBIBLE_SSH_PUB` | yes | The matching public key; registered as the deploy key | `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI… getbible-builder` |
| `GETBIBLE_GIT_USER` | yes | Author and committer name of the downstream commit | `getBible Builder` |
| `GETBIBLE_GIT_EMAIL` | yes | Author and committer email of the downstream commit; must belong to the GPG key | `builder@getbible.net` |
| `GETBIBLE_BOOKMARKS_REPO` | no | Override the downstream repository | `git@github.com:getbible/bookmarks-staging.git` |
| `GETBIBLE_BOOKMARKS_BRANCH` | no | Override the downstream branch | `staging` |

The six required secrets are consumed by
[`octoleo/git-user`](https://github.com/octoleo/git-user), which installs the
keys, trusts GitHub's SSH host key and configures git to sign commits. When
any of them is missing the action stops before anything is cloned, with a
message such as `"--gpg-key" requires a non-empty option argument`, and
nothing reaches the downstream repository.

The two optional secrets feed environment variables that `run.sh` reads. The
workflow applies the getBible defaults when a secret is absent:

| Environment variable | Set by the workflow to | Default when the secret is absent |
|---|---|---|
| `BOOKMARKS_REPO` | `GETBIBLE_BOOKMARKS_REPO` | `git@github.com:getbible/bookmarks.git` |
| `BOOKMARKS_BRANCH` | `GETBIBLE_BOOKMARKS_BRANCH` | `main` |

`run.sh` also uses `GITHUB_SHA`, which GitHub Actions provides, to name the
source commit in the downstream commit message.

Creating the deploy key, if a new one is needed:

```bash
ssh-keygen -t ed25519 -C "getbible-builder" -N "" -f getbible-builder
# getbible-builder      -> GETBIBLE_SSH_KEY
# getbible-builder.pub  -> GETBIBLE_SSH_PUB, and Settings → Deploy keys on getbible/bookmarks
#                          with "Allow write access" ticked
```

## What the workflow does

1. Checks out this repository and sets up Python 3.13.
2. Configures the getBible git identity with `octoleo/git-user`.
3. Runs `./run.sh --pull --push`.

Runs are serialised by a concurrency group, so two pushes in quick succession
publish one after the other and never race on the downstream branch. The
workflow also accepts manual dispatch from the Actions tab, which is the way
to publish after adding the secrets or after fixing a failed run.

## What `run.sh` does

```bash
./run.sh [--repo=URL] [--branch=NAME] [--target=DIR] [--pull] [--push] [--dry-run]
```

| Option | Meaning |
|---|---|
| `--repo=URL` | Downstream repository (default `$BOOKMARKS_REPO`, then `git@github.com:getbible/bookmarks.git`) |
| `--branch=NAME` | Downstream branch (default `$BOOKMARKS_BRANCH`, then `main`) |
| `--target=DIR` | Local checkout of the downstream repository, relative to the caller's directory (default `./bookmarks`, ignored by git) |
| `--pull` | Reset an existing checkout to the remote branch first; a missing checkout is always cloned |
| `--push` | Push the commit when something changed |
| `--dry-run` | Build and report, leave the changes staged, never commit or push |

Steps:

1. `python3 src/builder.py validate`. Any rule violation stops here.
2. Clone the downstream repository (shallow) or, with `--pull`, fetch and
   reset the checkout to the remote branch, discarding whatever a previous dry
   run left behind.
3. `python3 src/builder.py build --output <target>/v1`. The previously
   published `index.json` supplies the last version and checksum.
4. Stage `v1/`. When the rendered files are byte-identical to what is
   published, print `Nothing to commit` and stop.
5. Commit `Update bookmarks API to catalogue version N`, with the source
   commit in the body, and push with `--push`.

Only `v1/` is touched. The downstream README and license are never rewritten.

### Version and checksum

| Situation | `catalog_version` in the new `index.json` |
|---|---|
| No published `index.json` | 1 |
| Same checksum as published | unchanged, and no commit is made |
| Different checksum | previous + 1 |
| `index.json` present but unreadable or invalid | the build fails |

The checksum is the SHA-256 of `v1/all.json`. See
[ARCHITECTURE.md](ARCHITECTURE.md#versioning-and-checksums).

## Running it yourself

Against a throwaway repository, no secrets needed:

```bash
git init --initial-branch=main /tmp/downstream
git -C /tmp/downstream commit --allow-empty -m "Initial commit"
./run.sh --target=/tmp/downstream --dry-run
```

Against the real downstream repository from a machine that has push access:

```bash
./run.sh --pull --push
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `"--gpg-key" requires a non-empty option argument` in the identity step | A required secret is missing or empty | Add the six required secrets, then re-run the workflow from the Actions tab |
| `Permission denied (publickey)` or `ERROR: Repository not found` while cloning | The SSH key is not registered as a deploy key on the downstream repository, or has no write access | Add `GETBIBLE_SSH_PUB` as a deploy key with write access on `getbible/bookmarks` |
| `error: <file>: <rule>` before anything is cloned | The sources violate a rule | Fix the file; the message names the file and the rule ([DATA.md](DATA.md)) |
| `refusing to reset the published version` | The downstream `v1/index.json` exists but is damaged | Restore it from the downstream history, then re-run |
| The run succeeds but prints `Nothing to commit` | The content did not change | Expected; only content changes are published |
| `! [rejected]` on push | Someone pushed to the downstream branch during the run | Re-run the workflow; `--pull` resets the checkout first |

## Serving

Point a static file server at the downstream repository's `v1/` directory.
The documents are plain JSON with stable paths, so a plain nginx `root` with
`gzip` and long cache headers is enough; the downstream README describes
every file. Updating the server is a `git pull` of the downstream
repository, on a timer or from a webhook on its `push` event.
