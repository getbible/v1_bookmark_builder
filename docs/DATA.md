# Data and editing contract

The catalogue is three kinds of JSON files under `data/`. Everything the
builder publishes is derived from them, and everything a contributor, the
robot or the app changes is a change to one of them. The builder refuses to
publish anything that violates the rules below, so a bad edit fails the build
instead of reaching consumers.

## Files

### `data/topics.json`

```json
{
  "schema_version": 1,
  "topics": [
    {
      "id": "gods-judgment",
      "name": "God's Judgment",
      "color": "#fb7185",
      "aliases": ["God's Judgement"],
      "default": true
    }
  ]
}
```

| Field | Rule |
|---|---|
| `id` | Lowercase slug, letters, digits and single hyphens, at most 80 characters. Stable: consumers store it. |
| `name` | English display name, at most 80 characters, letters, digits, spaces and `& ' ( ) : ? -`. Unique across all names and aliases, case-insensitively. |
| `color` | Six-digit lowercase hex colour such as `#93c5fd`. |
| `aliases` | Other English wordings, same rule as `name`, sorted, at most 20, never repeating the name or each other (case-insensitively). Keep the previous wording here when you rename a topic. |
| `default` | `true` when the topic belongs to the starter set an application shows before any personal choice. |

At most 1,000 topics. The builder writes them sorted by `id`; any order is
accepted on input.

### `data/links/<id>.json`

One file per topic, named after the topic id, listing the verses linked to it:

```json
{
  "schema_version": 1,
  "topic": "gods-judgment",
  "verses": [
    [45, 2, 5],
    [58, 9, 27]
  ]
}
```

A verse is `[book, chapter, verse]` in the 66-book Protestant canon: book 1 is
Genesis and 66 is Revelation, chapters are bounded by the real chapter count
of the book, verses are 1 to 2,000 (loose on purpose because versification
differs between translations). The coordinates are translation independent;
no Scripture text is stored. Verses are strictly ascending with no duplicates.
A topic whose links file does not exist yet simply has no verses; the builder
creates an empty file for it when it normalises the sources. A links file for
a topic that is not in `topics.json` is an error. At most 100,000 links in
total.

### `data/locales/<locale>.json`

One file per locale, named after the locale code:

```json
{
  "schema_version": 1,
  "locale": "fr",
  "name": "French",
  "topics": {
    "gods-judgment": "Jugement de Dieu",
    "grace": "Grâce"
  }
}
```

| Field | Rule |
|---|---|
| `locale` | Lowercase BCP 47 style tag: `fr`, `zh-hant`, `pt-br`. `en` is reserved; English names live in `topics.json`. |
| `name` | Optional English name of the language. |
| `topics` | Topic id to translated name, sorted by id. Names are trimmed, NFC normalised, up to 120 characters, no control characters. A locale may cover only part of the catalogue; consumers fall back to English. |

## Operations

| Change | Files |
|---|---|
| Add a topic | Add the entry to `topics.json`; add `links/<id>.json`; optionally add names to locale files. |
| Add or remove verses | Edit `links/<id>.json`, keeping the list sorted and unique. |
| Rename a topic | Change `name` in `topics.json` and add the previous wording to `aliases`. The id never changes. |
| Recolour a topic | Change `color` in `topics.json`. |
| Delete a topic | Remove the entry from `topics.json`, delete `links/<id>.json`, remove the id from every locale file. The next build drops it everywhere; the id may be reused later. |
| Translate names | Edit or add `locales/<locale>.json`. |

Run `python3 -m bookmark_builder validate` before opening a pull request, and
`python3 -m bookmark_builder normalize` to rewrite the files in the builder's
canonical formatting (sorted keys, one verse per line, trailing newline). CI
runs the same validation, and the publication workflow refuses to push when it
fails.

## Editing through the GitHub API

Applications write to this repository with the GitHub contents API. Each
request replaces one file atomically, which is why the layout keeps one file
per topic and per locale: two applications editing different topics never
conflict, and a conflict on the same file is reported instead of silently
merged.

Use a fine-grained personal access token or a GitHub App installation that
grants **Contents: read and write** on this repository only. Write directly to
the default branch for trusted automation, or to a branch followed by a pull
request when a person should review first.

1. Read the current file to obtain its blob `sha`:

   ```http
   GET /repos/getbible/v1_bookmark_builder/contents/data/links/grace.json?ref=main
   ```

2. Decode `content` (base64), apply the change, keep the verse list sorted and
   unique, and encode the new document.

3. Write it back with the `sha` from step 1 and a descriptive message:

   ```http
   PUT /repos/getbible/v1_bookmark_builder/contents/data/links/grace.json
   {
     "message": "Add Ephesians 2:8-9 to grace",
     "content": "<base64 document>",
     "sha": "<sha from step 1>",
     "branch": "main"
   }
   ```

   A `409 Conflict` means the file changed since step 1: read it again, reapply
   the change and retry. A new file (a new topic's links file, a new locale)
   is created with the same request without `sha`. To delete a topic's links
   file use `DELETE` with the `sha`.

4. Every push to the default branch triggers the publication workflow. The
   downstream repository is updated a minute or two later when the content
   changed.

Render the JSON exactly as the builder does when you can: two-space indented
objects, verse triples on one line, a trailing newline. The builder accepts
any valid JSON with the right keys; a maintainer can run
`python3 -m bookmark_builder normalize` at any time to bring every file back
to the canonical formatting so diffs stay tidy.

## Robot contribution bundles

The getBible robot's moderation tooling exports accepted changes as a schema
version 1 bundle (`schema/contribution-bundle.schema.json`). Apply one locally:

```bash
python3 -m bookmark_builder import-bundle --check exported.json   # validate only
python3 -m bookmark_builder import-bundle exported.json           # write data/
```

A bundle may create topics, extend the aliases of existing topics, and add or
remove verse links (at most 10,000 additions and 10,000 removals per bundle).
It cannot change an established topic's id, name or colour; those are edited
in `topics.json` deliberately.

## Schemas

`schema/` holds JSON Schemas for the three source documents, the bundle and
every generated API document. The test suite validates the rendered output of
both a fixture catalogue and the real `data/` against them.
