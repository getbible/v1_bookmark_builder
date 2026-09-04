# Contributing to the catalogue

The catalogue grows by changing files under `data/` in this repository.
There are two routes, and applications such as the getBible robot and the
getBible app use the same ones a person does:

| Route | Who | What happens |
|---|---|---|
| Branch and pull request | Anyone with read access (fork) or write access (branch); applications that want a human to review first | CI validates the change; a maintainer merges; the merge publishes |
| Direct write to `main` | Collaborators with write access and applications holding a token with **Contents: write** on this repository | The push publishes immediately, no review step |

Both end the same way: a push to the default branch runs the publication
workflow, which validates the sources, renders `v1/` and commits it to
`getbible/bookmarks` when the content changed. See
[PUBLISHING.md](PUBLISHING.md).

The file formats and every rule are in [DATA.md](DATA.md). Read at least its
rule summary before writing; a change that violates a rule fails the build
and is not published until fixed.

## Route 1: git

```bash
git clone https://github.com/getbible/v1_bookmark_builder.git
cd v1_bookmark_builder
git switch -c add-john-3-16-to-grace

# edit data/links/grace.json, data/topics.json, data/locales/*.json ...

python3 src/builder.py validate
python3 src/builder.py normalize          # optional, keeps the diff tidy
git add data
git commit -m "Add John 3:16 to grace"
git push -u origin add-john-3-16-to-grace
```

Open a pull request against `main`. CI runs the same validation plus the
tests and a publication dry run. Collaborators with write access may instead
commit to `main` directly; the push publishes.

Keep one logical change per commit. Adding a topic means editing
`topics.json` and creating its links file in the same commit, so no build
ever sees one without the other.

## Route 2: the GitHub API

Applications write files with GitHub's REST API. Two mechanisms cover every
operation:

- the **contents API** replaces or creates one file per request, each
  request becoming one commit. Use it for single-file changes: adding or
  removing verses, translating names.
- the **Git Data API** builds one commit from several files. Use it when an
  operation must touch more than one file, such as creating or deleting a
  topic.

Both can target `main` directly or a branch that is then opened as a pull
request.

### Authentication

Use a fine-grained personal access token or a GitHub App installation token:

| Setting | Value |
|---|---|
| Repository access | Only `getbible/v1_bookmark_builder` |
| Permissions | **Contents: Read and write**. Add **Pull requests: Read and write** when the application opens pull requests |

Send every request with these headers:

```http
Authorization: Bearer <token>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
```

On the contents API the token owner becomes the committer. Pass an `author`
object on writes so the commit names the person behind the change, for
example the contributor whose bookmark is being shared:

```json
"author": { "name": "Jane Contributor", "email": "jane@example.org" }
```

A token with Contents: write on this repository can change the catalogue
without review. Keep it on the server side of the application, never in a
client, and scope it to this repository only.

### Read a file

```http
GET /repos/getbible/v1_bookmark_builder/contents/data/links/grace.json?ref=main
```

The response carries the file as base64 in `content` and its blob `sha`.
Decode the content, and keep the `sha`: every update must quote it. For a
file above 1 MB the contents endpoint returns an empty `content` with
`encoding: "none"`; read such a file through
`GET /repos/getbible/v1_bookmark_builder/git/blobs/<sha>` instead, which
serves up to 100 MB. A links file at the 100,000-verse limit is roughly
1.5 MB.

### Update or create one file (contents API)

```http
PUT /repos/getbible/v1_bookmark_builder/contents/data/links/grace.json
```

```json
{
  "message": "Add John 3:16 to grace",
  "content": "<base64 of the complete new document>",
  "sha": "<sha from the read>",
  "branch": "main",
  "author": { "name": "Jane Contributor", "email": "jane@example.org" }
}
```

- `200` means updated, `201` means created (omit `sha` to create a file that
  does not exist yet).
- `409 Conflict` means either that the file changed since it was read or
  that another commit landed on the branch while GitHub was processing the
  request. In both cases read the file again, reapply the change to the
  fresh content, and retry. Every contents-API write is its own commit on
  the branch, and GitHub documents that parallel writes to one branch
  conflict even when they touch different files, so an application must
  issue its contents-API writes one at a time and use the Git Data route
  below for a batch.
- `422` means the request itself is malformed, most often a missing `sha`
  for an existing file or a bad base64 body.

Always send the complete document. The contents API replaces the whole file;
it does not merge.

### Delete one file (contents API)

```http
DELETE /repos/getbible/v1_bookmark_builder/contents/data/links/old-topic.json
```

```json
{ "message": "Delete old-topic links", "sha": "<sha from the read>", "branch": "main" }
```

Deleting a links file alone is not a valid catalogue change: the topic must
leave `topics.json` and every locale in the same commit. Use the Git Data
API for that.

### Several files in one commit (Git Data API)

Creating a topic touches `topics.json` and a new links file; deleting one
touches `topics.json`, its links file and every locale that translates it.
Make those one commit:

1. Read the branch head and its tree:

   ```http
   GET /repos/getbible/v1_bookmark_builder/git/ref/heads/main
   GET /repos/getbible/v1_bookmark_builder/git/commits/<head sha>
   ```

2. Read the files you will change (contents API with `ref=<head sha>`),
   apply the changes in memory, validate.

3. Create a blob for every changed file:

   ```http
   POST /repos/getbible/v1_bookmark_builder/git/blobs
   { "content": "<file text>", "encoding": "utf-8" }
   ```

4. Create a tree on top of the head's tree. A `sha` of `null` deletes a path:

   ```http
   POST /repos/getbible/v1_bookmark_builder/git/trees
   {
     "base_tree": "<tree sha of the head commit>",
     "tree": [
       { "path": "data/topics.json",          "mode": "100644", "type": "blob", "sha": "<blob>" },
       { "path": "data/links/new-topic.json", "mode": "100644", "type": "blob", "sha": "<blob>" },
       { "path": "data/links/old-topic.json", "mode": "100644", "type": "blob", "sha": null }
     ]
   }
   ```

5. Create the commit and move the branch:

   ```http
   POST /repos/getbible/v1_bookmark_builder/git/commits
   { "message": "Add topic new-topic", "tree": "<new tree>", "parents": ["<head sha>"],
     "author": { "name": "Jane Contributor", "email": "jane@example.org" },
     "committer": { "name": "getBible App", "email": "app@getbible.net" } }

   PATCH /repos/getbible/v1_bookmark_builder/git/refs/heads/main
   { "sha": "<new commit>" }
   ```

   Unlike the contents API, this endpoint copies `author` into `committer`
   when `committer` is omitted, so pass the application's identity
   explicitly to keep it in the history. The ref update is a fast-forward.
   A `422` here means the branch moved since step 1: start again from
   step 1. Nothing was published in between, because the commit is
   unreachable until the ref moves.

### Through a pull request instead of a direct write

Create a branch from the head, write to it, and open the pull request:

```http
POST /repos/getbible/v1_bookmark_builder/git/refs
{ "ref": "refs/heads/app/add-john-3-16-to-grace", "sha": "<head sha>" }

PUT /repos/getbible/v1_bookmark_builder/contents/data/links/grace.json
{ ..., "branch": "app/add-john-3-16-to-grace" }

POST /repos/getbible/v1_bookmark_builder/pulls
{ "title": "Add John 3:16 to grace", "head": "app/add-john-3-16-to-grace", "base": "main",
  "body": "Submitted from the getBible app on behalf of Jane Contributor." }
```

The Git Data recipe works the same way with the branch name in the `PATCH`
step. A maintainer reviews and merges; the merge publishes.

### After the write

The push starts the publication workflow within seconds; a run takes about
a minute. To confirm that a change is live, read the published index from
the downstream repository and compare it with what was read before the
write:

```http
GET /repos/getbible/bookmarks/contents/v1/index.json?ref=main
```

`catalog_version` increases by one and `checksum` changes for every content
change. The per-topic document `v1/topics/<id>.json` then carries the new
verse. If the run fails instead, the Actions tab of this repository shows
the validation error; the sources are still in the state the application
left them, so the fix is another write.

The two worked examples write with `json.dumps(..., indent=2)`, which puts
each coordinate of a verse on its own line. The builder accepts that, but
it is not the canonical layout
([DATA.md](DATA.md#checking-and-normalising)): the file's diff grows by
five lines per verse, and the next `normalize` run rewrites the file once.
An application that writes often should render one verse per line.

### Worked example: add a verse with `curl`

```bash
set -euo pipefail
REPO=getbible/v1_bookmark_builder
FILE=data/links/grace.json
API="https://api.github.com/repos/$REPO/contents/$FILE"
AUTH=(-H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json"
      -H "X-GitHub-Api-Version: 2022-11-28")

curl -sS --fail-with-body "${AUTH[@]}" "$API?ref=main" > current.json

python3 - current.json > body.json <<'PY'
import base64, json, sys
current = json.load(open(sys.argv[1]))
doc = json.loads(base64.b64decode(current["content"]))
verse = [43, 3, 16]
if verse not in doc["verses"]:
    doc["verses"].append(verse)
    doc["verses"].sort()
content = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
print(json.dumps({
    "message": "Add John 3:16 to grace",
    "content": base64.b64encode(content.encode()).decode(),
    "sha": current["sha"],
    "branch": "main",
    "author": {"name": "Jane Contributor", "email": "jane@example.org"},
}))
PY

curl -sS --fail-with-body "${AUTH[@]}" -X PUT "$API" --data-binary @body.json
```

`--fail-with-body` makes `curl` exit non-zero on any error status and print
the response, so a `409` stops the script; running it again reads the fresh
file and retries. The body goes through a file rather than a command line
argument, so a large links file is not limited by the shell's argument size.

### Worked example: create a topic atomically in Python

Standard library only, direct write to `main`, retried on a moved branch:

```python
import base64, json, urllib.error, urllib.request

API = "https://api.github.com/repos/getbible/v1_bookmark_builder"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Content-Type": "application/json",
}


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(API + path, data=data, headers=HEADERS, method=method)
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def read_text(path, ref):
    document = call("GET", f"/contents/{path}?ref={ref}")
    return base64.b64decode(document["content"]).decode()


def create_topic(topic, verses, author, committer):
    for _ in range(3):
        head = call("GET", "/git/ref/heads/main")["object"]["sha"]
        base_tree = call("GET", f"/git/commits/{head}")["tree"]["sha"]

        topics = json.loads(read_text("data/topics.json", head))
        if any(t["id"] == topic["id"] for t in topics["topics"]):
            raise ValueError(f"{topic['id']} already exists")
        topics["topics"].append(topic)
        topics["topics"].sort(key=lambda t: t["id"])
        links = {"schema_version": 1, "topic": topic["id"], "verses": sorted(verses)}

        blobs = {
            "data/topics.json": call(
                "POST",
                "/git/blobs",
                {
                    "content": json.dumps(topics, ensure_ascii=False, indent=2) + "\n",
                    "encoding": "utf-8",
                },
            )["sha"],
            f"data/links/{topic['id']}.json": call(
                "POST",
                "/git/blobs",
                {"content": json.dumps(links, indent=2) + "\n", "encoding": "utf-8"},
            )["sha"],
        }
        tree = call(
            "POST",
            "/git/trees",
            {
                "base_tree": base_tree,
                "tree": [
                    {"path": p, "mode": "100644", "type": "blob", "sha": s}
                    for p, s in blobs.items()
                ],
            },
        )["sha"]
        commit = call(
            "POST",
            "/git/commits",
            {
                "message": f"Add topic {topic['id']}",
                "tree": tree,
                "parents": [head],
                "author": author,
                "committer": committer,
            },
        )["sha"]
        try:
            call("PATCH", "/git/refs/heads/main", {"sha": commit})
            return commit
        except urllib.error.HTTPError as error:
            if error.code != 422:  # 422: the branch moved; rebuild on the new head
                raise
    raise RuntimeError("main kept moving; try again later")


create_topic(
    {"id": "mercy", "name": "Mercy", "color": "#fde68a", "aliases": [], "default": False},
    [[19, 23, 6], [49, 2, 4]],
    {"name": "Jane Contributor", "email": "jane@example.org"},
    {"name": "getBible App", "email": "app@getbible.net"},
)
```

The same shape deletes a topic: remove it from `topics.json`, add a tree
entry with `"sha": null` for its links file, and rewrite every locale file
that names it.

### Validating before writing

The build validates after the fact, but a failed build means the change is
not live until someone fixes it. Applications should check locally, in this
order, before writing:

1. The document is valid JSON with exactly the keys in [DATA.md](DATA.md).
2. Ids, names, colours and locale codes match the rule summary.
3. Verses are inside the canon (book 1 to 66, chapter within the book's
   count, verse 1 to 2,000), sorted and unique.
4. A new topic's name and aliases collide with nothing in `topics.json`,
   compared case-insensitively.

`schema/topics.schema.json`, `schema/links.schema.json` and
`schema/locale.schema.json` express steps 1 to 3 as JSON Schema and can be
loaded straight into a validator.

## Route 3: robot bundles

The getBible robot's moderation pipeline exports accepted changes as a
bundle ([DATA.md](DATA.md#robot-contribution-bundles)). A maintainer applies
it with `python3 src/builder.py import-bundle` and commits, or the robot's
publisher translates it into the file writes above and commits directly with
its own token.

## Attribution

Every commit records who made the change. When an application writes on
behalf of a person, put that person in the commit `author` and keep the
application's identity as the committer. The history of `data/` is the
catalogue's memory; nothing else records who contributed what.
