# Command line reference

The builder runs as a script from the repository root and needs Python 3.12
or newer, nothing else:

```bash
python3 src/builder.py [--data DIR] [-v] <command> [options]
```

| Global option | Meaning |
|---|---|
| `--data DIR` | Directory holding `topics.json`, `links/` and `locales/` (default `./data`) |
| `-v`, `--verbose` | Debug logging |
| `--version` | Print the builder version |

Every command exits with `0` on success and `1` on a rule violation, printing
`error: <reason>` on standard error. The reason names the file, the entry and
the rule, for example
`error: links/grace.json.verses must be strictly ascending without duplicates.`

## `validate`

Loads every source document, checks every rule in [DATA.md](DATA.md) and
prints a one-line summary:

```text
OK: 61 topics, 2155 verse links, 53 locales.
```

Run it before opening a pull request. CI and the publication workflow run
the same validation; a violation fails them.

## `normalize`

Loads the sources and writes them back in the builder's canonical formatting:
two-space indented objects, one verse triple per line, topics sorted by id,
locale entries sorted by topic id, a trailing newline, and an empty links
file for any topic that has none. It reports which files it rewrote:

```text
Normalized 2 source file(s): links/grace.json, topics.json
```

Use it after hand edits or after applications have written files through the
GitHub API, so review diffs stay minimal. Content never changes, only
formatting.

## `build`

Renders the complete API tree:

```bash
python3 src/builder.py build --output v1
```

| Option | Meaning |
|---|---|
| `--output DIR` | Directory to create or replace (default `./v1`). If it already holds an `index.json`, that file supplies the previously published version and checksum |
| `--check` | Do not write; report whether `--output` already matches a fresh build (exit `1` and list the stale paths when it does not) |

Output:

```text
Generated 1376 files into v1 (catalogue version 2, checksum 8e5ac246…, content changed).
```

`content unchanged` means the checksum equals the published one and the
version was kept. The tree is written beside the target and swapped in
atomically, so a failed build never leaves a half-written directory.

## `import-bundle`

Applies a getBible robot contribution bundle (schema version 1, see
[DATA.md](DATA.md#robot-contribution-bundles)) to the sources:

```bash
python3 src/builder.py import-bundle --check exported.json   # validate only
python3 src/builder.py import-bundle exported.json           # write data/
```

The command reports what it would do or did: topics created, aliases
extended, verse links added and removed. A bundle that is already fully
applied is a no-op.

## `run.sh`

The publication script wraps `validate` and `build` around a checkout of the
downstream repository and commits the result. It is documented in
[PUBLISHING.md](PUBLISHING.md).
