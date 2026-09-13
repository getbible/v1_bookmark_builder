# OpenAPI reference

Every normal build generates `openapi.json` alongside the API's other JSON
files:

```bash
python3 src/builder.py build --output v1
```

The result is `v1/openapi.json`, an OpenAPI 3.1.1 document. The standard
publication workflow sends it to `getbible/bookmarks` with the rest of
`v1/`; no separate generation or publication step is needed. Consumers can
discover its relative path in `index.json` at `resources.openapi`.

## Importing the description

Use a client or documentation viewer that supports OpenAPI 3.1. Import the
published `openapi.json` URL, or download the file and import the local
copy. The response schemas are embedded and use local component references,
so schema loading does not depend on GitHub or other external URLs.

The server URL is `./`: when the specification is loaded from its published
URL, requests resolve against the directory containing `openapi.json`.
This works whether the server mounts the API at `/v1/` or another path.
When importing a downloaded file or pasting it into an editor, set the
client's base URL, or override `servers[0].url` in that imported copy, to
the actual HTTP URL serving the generated directory. A local file does not
identify the production server. No production hostname is assumed by the
builder.

## Endpoints

All paths below are relative to the API directory. Every operation is a
GET of a static JSON file; there are no request bodies or query parameters.

| Path | Response |
|---|---|
| `/index.json` | Schema and catalogue versions, content checksum, counts, locale codes and resource paths |
| `/all.json` | Complete catalogue: all topic metadata and verse coordinates, plus all locale documents |
| `/catalog.json` | All topic metadata and verse coordinates, without locale documents |
| `/topics.json` | Topic summaries, with a verse-link count for each topic |
| `/topics/{id}.json` | One topic, its available translated names and verse coordinates |
| `/verses/{book}.json` | Topic ids indexed by chapter and verse for one book |
| `/verses/{book}/{chapter}.json` | Topic ids indexed by verse for one chapter |
| `/locales.json` | Available locale codes, language names and translation counts |
| `/locales/{locale}.json` | Translated topic names for one locale |
| `/checksums.json` | SHA-256 of every other generated file, keyed by relative path |
| `/openapi.json` | This API's OpenAPI description |

Topic ids are lowercase slugs from `/topics.json`; display names and aliases
are not endpoint identifiers. Locale codes are lowercase tags from
`/locales.json`, such as `en`, `fr` and `zh-hant`.

Book numbers follow the 66-book Protestant canon, from 1 (Genesis) to
66 (Revelation). A chapter number must exist within the requested book.
Verse coordinates are three-element integer arrays in the order
`[book, chapter, verse]`; they carry no Scripture text or translation id.
Verse numbers are accepted from 1 to 2,000 to accommodate differences in
versification. The schema preserves the separate bounds of all three
positions.

## Reading the responses

The `verses` field in a topic summary is an integer count. In
`/catalog.json`, `/all.json` and `/topics/{id}.json`, it is an array of
coordinates. The index's `counts.verses` counts topic–verse associations:
one Bible verse linked to two topics contributes two to that count.

Every canonical book and chapter has a generated file, including those
with no topic associations. Reverse indexes are sparse: missing chapter
or verse keys mean there are no associations at that location. A valid
chapter with no associations returns an empty `verses` object. Object keys
for chapters and verses are JSON strings; the response's `book` and
`chapter` fields are integers.

English (`en`) is generated from the canonical topic names and always
covers the complete catalogue. Other locales may cover only some topics;
consumers should fall back to the English topic name when a translation is
missing. The builder does not fill translations automatically or negotiate
languages from request headers. Individual topic responses include a
`names` map containing only available translations, including English.

In `/locales/{locale}.json`, the language `name` can be absent. In
`/locales.json`, each entry always includes `name`, which is `null` when no
language name was supplied. The locale's `topics` map contains topic ids
and translated display names.

The builder provides no write endpoint or authentication system. Missing
topic ids, unavailable locale codes and invalid book/chapter paths do not
have generated files. Their HTTP error response body, along with cache
headers, CORS and other HTTP behavior, depends on the static file server.
The OpenAPI description does not prescribe a JSON error envelope.

## Examples and schema references

Individual topic, book, chapter and locale examples are selected from the
current build. Responses of at most 16,384 bytes are embedded in the
specification; larger responses use a relative `externalValue` link to
the complete generated file. An empty catalogue has no topic example.
Examples therefore follow the actual source catalogue instead of a
separately maintained sample.

The index, aggregate resources and checksum manifest reference the actual
generated JSON through relative `externalValue` example URLs. These links
keep large responses out of the specification and refer to the full
published responses. A viewer may need network access to display them;
when working with a downloaded specification, retain the generated files
beside it or resolve the links against the published specification URL.

OpenAPI 3.1 is required because the existing response schemas use JSON
Schema Draft 2020-12 features, including positional verse-coordinate
schemas and nullable language names. All schema references within the
generated document resolve locally; external example links are response
data, not schema dependencies.

## Checksums and publication

`index.json.checksum` is the SHA-256 of the exact bytes of `all.json`,
including its formatting and final newline. `catalog_version` increments
when that content checksum changes between published builds. The OpenAPI
description is not included in this content checksum.

`checksums.json` includes `openapi.json` and every other generated file
except itself. Updates to the generated description are published even
when the catalogue content and `catalog_version` are unchanged. An
identical rebuild produces identical files, and `build --check` detects a
missing or stale OpenAPI document along with any other stale output.
