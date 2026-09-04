# Data contract

The catalogue is three kinds of JSON files under `data/`. Everything the
builder publishes is derived from them, and everything a person or an
application changes is a change to one of them. The builder refuses to
publish anything that violates the rules below, so a bad edit fails the
build instead of reaching consumers. Applications that write these files
should apply the same rules before writing; the summary at the end of this
page is meant to be copied into their validators.

## `data/topics.json`

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
| `schema_version` | Always `1` |
| `id` | Lowercase slug: letters, digits and single hyphens, no leading or trailing hyphen, 1 to 80 characters. Unique. Stable: consumers store it, so never rename an id; create a new topic instead |
| `name` | English display name, 1 to 80 characters, letters, digits, single spaces and `& ' ( ) : ? -`, starting with a letter or digit and ending with a letter, digit or `)`. Unique across every name and alias of every topic, compared case-insensitively |
| `color` | Six-digit lowercase hex colour, `#rrggbb` |
| `aliases` | Other English wordings under the same rule as `name`, sorted, at most 20, never repeating the name or each other case-insensitively. When a topic is renamed the previous wording goes here so stored references keep resolving |
| `default` | `true` when the topic belongs to the starter set an application shows before the reader has made any choice |

At most 1,000 topics. The builder writes the list sorted by `id`; any order
is accepted on input. No other fields are allowed.

## `data/links/<id>.json`

One file per topic, named after the topic id:

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

| Field | Rule |
|---|---|
| `topic` | Must equal the file name without `.json` and name a topic in `topics.json` |
| `verses` | `[book, chapter, verse]` triples, strictly ascending, no duplicates |

A verse coordinate is translation independent and carries no Scripture text:

| Part | Range |
|---|---|
| `book` | 1 to 66 in Protestant canon order: 1 Genesis … 39 Malachi, 40 Matthew … 66 Revelation (the table is in `src/canon.py` and in the downstream README) |
| `chapter` | 1 to the chapter count of that book (Psalms has 150, Revelation 22) |
| `verse` | 1 to 2,000, deliberately loose because versification differs between translations |

A topic whose links file does not exist has no verses; `normalize` creates an
empty file for it. A links file for a topic that is not in `topics.json` is
an error. At most 100,000 links in total across the catalogue.

## `data/locales/<locale>.json`

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
| `locale` | Lowercase BCP 47 style tag: two or three letters, optionally followed by `-` and two to eight letters or digits (`fr`, `zh-hant`, `pt-br`). Must equal the file name. `en` is reserved: English names live in `topics.json` and the builder derives `locales/en.json` from them |
| `name` | Optional English name of the language, up to 80 characters |
| `topics` | Topic id to translated name, keys sorted. Names are trimmed, NFC normalised, 1 to 120 characters, no control characters. A locale may cover only part of the catalogue; consumers fall back to the English name |

At most 500 locales. A locale must not name a topic that does not exist.

## Operations

| Change | Files to touch |
|---|---|
| Add a topic | Append the entry to `topics.json`; create `links/<id>.json` (may be empty); optionally add its name to locale files |
| Add or remove verses | Edit `links/<id>.json`, keeping the list sorted and unique |
| Rename a topic | Change `name` in `topics.json` and add the previous wording to `aliases`. Never change the id |
| Recolour a topic | Change `color` in `topics.json` |
| Delete a topic | Remove the entry from `topics.json`, delete `links/<id>.json`, remove the id from every locale file. The next build drops it everywhere; the id may be reused later |
| Translate names | Edit or add `locales/<locale>.json` |

Every change should be one commit, whether it touches one file or several,
so that a build never sees a topic without its links file or a links file
without its topic. [CONTRIBUTING.md](CONTRIBUTING.md) shows how to do that
both with git and with the GitHub API.

## Checking and normalising

```bash
python3 src/builder.py validate     # every rule above, exit 1 with the reason on failure
python3 src/builder.py normalize    # rewrite data/ in canonical formatting
```

The builder accepts any valid JSON with the right keys, but the canonical
formatting keeps diffs small: two-space indented objects, one verse triple
per line, sorted topics and locale entries, a trailing newline. Applications
that render their own JSON should follow it; a maintainer can run
`normalize` at any time to restore it.

## Robot contribution bundles

The getBible robot's moderation tooling exports accepted changes as a schema
version 1 bundle:

```json
{
  "schema_version": 1,
  "topics": [
    { "id": "prayer-and-fasting", "name": "Prayer and Fasting", "color": "#93c5fd", "aliases": [] }
  ],
  "associations": {
    "add": [ { "topic_id": "prayer-and-fasting", "book": 40, "chapter": 6, "verse": 16 } ],
    "remove": []
  }
}
```

Apply one locally with `python3 src/builder.py import-bundle exported.json`
(`--check` validates without writing). A bundle may create topics, extend
the aliases of existing topics, and add or remove verse links, at most
10,000 additions and 10,000 removals per bundle. It cannot change an
established topic's id, name or colour; those are edited in `topics.json`
deliberately. A coordinate cannot be both added and removed in one bundle.
The schema is `schema/contribution-bundle.schema.json`.

An application that speaks the bundle format can also translate a bundle
into file edits itself: each `topics` entry becomes an entry in
`topics.json`, each `associations.add` becomes a line in the topic's links
file, each `associations.remove` removes one.

## Schemas

`schema/` holds JSON Schemas (draft 2020-12) for the three source documents,
the bundle and every generated API document. The test suite validates the
rendered output of both a fixture catalogue and the real `data/` against
them. Applications may use the source schemas to validate a document before
writing it, but note that uniqueness across files (a name used by two
topics, a links file for an unknown topic) is only checked by `validate`.

## Rule summary for validators

```text
topic id        ^[a-z0-9]+(?:-[a-z0-9]+)*$            max 80, unique
english name    ^[A-Za-z0-9][A-Za-z0-9 &'():?-]*[A-Za-z0-9)]$   max 80, no double spaces,
                unique across all names and aliases, case-insensitive
colour          ^#[0-9a-f]{6}$
aliases         same rule as name, sorted, unique, max 20, never equal to the name
locale code     ^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$        never "en"
translated name 1..120 chars, trimmed, NFC, no control characters
verse           [book 1..66, chapter 1..chapters(book), verse 1..2000]
verses list     strictly ascending, no duplicates
limits          1000 topics, 100000 links, 500 locales
```
