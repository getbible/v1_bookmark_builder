"""Describe the generated static API using its existing JSON Schemas.

The result is self-contained: schema references are local to the OpenAPI
document. Examples come from this build, and no timestamp or published
catalogue version is embedded, so documentation does not disrupt rebuilds.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from canon import BOOK_CHAPTER_COUNTS, BOOK_NAMES
from catalog import ENGLISH_LOCALE, CatalogError

OPENAPI_VERSION = "3.1.1"
SCHEMA_ROOT = Path(__file__).resolve().parent.parent / "schema"
SCHEMA_FILES = {
    "Index": "api/index.schema.json",
    "All": "api/all.schema.json",
    "Catalog": "api/catalog.schema.json",
    "Topics": "api/topics.schema.json",
    "Topic": "api/topic.schema.json",
    "Book": "api/book.schema.json",
    "Chapter": "api/chapter.schema.json",
    "Locales": "api/locales.schema.json",
    "Locale": "locale.schema.json",
    "Checksums": "api/checksums.schema.json",
}

# Resource keys match render.RESOURCES. Keeping the URL templates in the
# renderer avoids publishing paths that the builder does not actually emit.
OPERATIONS = {
    "index": (
        "Discovery",
        "Discover the catalogue and resource paths",
        "Resource paths are relative to this directory. counts.verses counts topic-to-verse "
        "associations, not distinct verses. checksum is the SHA-256 of the exact all.json bytes. "
        "catalog_version increments when that content checksum changes; documentation-only "
        "changes do not increment it. schema_version describes the payload format.",
    ),
    "all": (
        "Topics",
        "Download the complete catalogue and all translations",
        "Contains all topic metadata and verse coordinates, plus every locale's names. "
        "This is the content document hashed by index.json. No Scripture text is included.",
    ),
    "catalog": (
        "Topics",
        "Download every topic with its verse coordinates",
        "The same topics array as all.json, without locale documents. Verse coordinates are "
        "translation-independent [book, chapter, verse] triples in the 66-book Protestant canon, "
        "sorted without duplicates within a topic. No Scripture text is included.",
    ),
    "topics": (
        "Topics",
        "List topics with verse counts",
        "Topic summaries use an integer verses count instead of the coordinate arrays returned "
        "by catalog.json and individual topic files. Use the stable id to request a topic. "
        "Names and aliases are English display text, not alternative URL identifiers.",
    ),
    "topic": (
        "Topics",
        "Read one topic and its translated names",
        "Returns metadata, all verse coordinates, and names keyed by the locales that translate "
        "this topic. English (en) is always included. For a missing translation the client "
        "should display the English name. Deleted or unknown topic ids have no file.",
    ),
    "book": (
        "Verse lookup",
        "Find topics associated with verses in a book",
        "A file exists for each of the 66 books. chapters maps chapter-number strings to "
        "verse-number strings to sorted topic-id arrays. Only linked chapters and verses "
        "appear in the maps. An empty chapters object means no associations in the book.",
    ),
    "chapter": (
        "Verse lookup",
        "Find topics associated with verses in a chapter",
        "Every valid canonical chapter has a file, even when verses is empty. Keys are verse "
        "numbers as strings; values are sorted topic-id arrays. A missing verse key means "
        "no associations. A chapter beyond the selected book's chapter count has no file.",
    ),
    "locales": (
        "Translations",
        "List available locales and translation coverage",
        "Each entry gives the locale code, its English language name (null if unrecorded), "
        "and the number of topic names translated. English (en) is always complete; other "
        "locales may translate only part of the catalogue.",
    ),
    "locale": (
        "Translations",
        "Read topic names for one locale",
        "topics maps stable topic ids to translated names. name is omitted when no language "
        "name is recorded. en is derived from the English topic names and is always present. "
        "Other locales may be partial. Clients must implement English fallback; requesting "
        "an unavailable locale does not automatically return English.",
    ),
    "checksums": (
        "Discovery",
        "Read SHA-256 hashes for the generated files",
        "files maps relative paths to SHA-256 hashes of the exact published bytes. Includes "
        "index.json and openapi.json; excludes checksums.json itself to avoid self-reference. "
        "Use this manifest to verify downloads from the same build.",
    ),
    "openapi": (
        "Discovery",
        "Read this OpenAPI description",
        "Generated with the API on every build. Describes the available GET routes, path "
        "parameters, response schemas and examples. Response schemas are embedded with "
        "local references so schema resolution does not require another download.",
    ),
}


def build_openapi(
    resources: Mapping[str, str], files: Mapping[str, bytes], *, api_version: str
) -> dict[str, Any]:
    """Build the description after index.json and before checksums.json."""
    schemas = _load_schemas()
    parameters = _parameters(schemas, files, resources)
    paths: dict[str, Any] = {}
    for resource, path in resources.items():
        tag, summary, description = OPERATIONS[resource]
        media: dict[str, Any] = {
            "schema": (
                {"type": "object", "description": "An OpenAPI 3.1 description."}
                if resource == "openapi"
                else {"$ref": f"#/components/schemas/{resource.capitalize()}"}
            )
        }
        example = _example(resource, path, files, parameters)
        if example is not None:
            media["examples"] = {"published": example}
        operation: dict[str, Any] = {
            "operationId": f"get{resource.capitalize()}",
            "tags": [tag],
            "summary": summary,
            "description": description,
            "responses": {
                "200": {
                    "description": "The published JSON document.",
                    "content": {"application/json": media},
                },
                "404": {"$ref": "#/components/responses/NotFound"},
            },
        }
        path_parameters = [
            {"$ref": f"#/components/parameters/{name}"}
            for name in parameters
            if "{" + name + "}" in path
        ]
        if path_parameters:
            operation["parameters"] = path_parameters
        paths["/" + path] = {"get": operation}
    return {
        "openapi": OPENAPI_VERSION,
        "jsonSchemaDialect": "https://json-schema.org/draft/2020-12/schema",
        "info": {
            "title": "getBible Bookmarks API",
            "version": api_version,
            "description": (
                "Public, read-only static JSON API for Bible topic bookmarks. Start with "
                "index.json for discovery, topics.json for topic summaries, and a topic or "
                "chapter file for its associations. No API key, request body, pagination or "
                "query filtering is required. Changes are made through the source repository, "
                "not through HTTP write operations. Verse references carry no Scripture text. "
                "The server URL is relative to this document's directory. When importing a "
                "local copy into a tool, set the server URL to the directory hosting these "
                "JSON files. HTTP caching, CORS and error bodies are controlled by that host."
            ),
            "license": {
                "name": "Apache License 2.0",
                "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
            },
        },
        "servers": [
            {"url": "./", "description": "Directory containing openapi.json and index.json"}
        ],
        "security": [],
        "tags": [
            {"name": "Discovery", "description": "Discover resources and verify downloads."},
            {"name": "Topics", "description": "English topic metadata and verse coordinates."},
            {"name": "Verse lookup", "description": "Look up topic ids by book and chapter."},
            {"name": "Translations", "description": "Translated topic names and coverage."},
        ],
        "externalDocs": {
            "description": "Builder and API documentation",
            "url": "https://github.com/getbible/v1_bookmark_builder/blob/main/docs/OPENAPI.md",
        },
        "paths": paths,
        "components": {
            "schemas": schemas,
            "parameters": parameters,
            "responses": {
                "NotFound": {
                    "description": (
                        "The requested static file is unavailable (for example an unknown "
                        "topic or locale, or an invalid book/chapter). The hosting server "
                        "determines the response body and content type; no JSON error "
                        "envelope is defined by this builder."
                    )
                }
            },
        },
    }


def _load_schemas() -> dict[str, Any]:
    documents: dict[str, Any] = {}
    for name, relative in SCHEMA_FILES.items():
        path = SCHEMA_ROOT / relative
        try:
            document = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError) as error:
            raise CatalogError(f"Cannot load OpenAPI response schema {path}: {error}") from error
        if not isinstance(document, dict) or not isinstance(document.get("$id"), str):
            raise CatalogError(f"OpenAPI response schema {path} must be an object with a $id.")
        documents[name] = document
    references = {
        document["$id"]: f"#/components/schemas/{name}" for name, document in documents.items()
    }
    return {name: _localize(document, references) for name, document in documents.items()}


def _localize(node: Any, references: Mapping[str, str]) -> Any:
    """Remove schema base URIs and replace source references with local ones."""
    if isinstance(node, list):
        return [_localize(value, references) for value in node]
    if not isinstance(node, dict):
        return node
    result: dict[str, Any] = {}
    for key, value in node.items():
        if key == "$id":
            continue
        if key == "$ref":
            if value not in references:
                raise CatalogError(f"Unmapped OpenAPI response schema reference: {value}")
            result[key] = references[value]
        else:
            result[key] = _localize(value, references)
    return result


def _parameters(
    schemas: Mapping[str, Any], files: Mapping[str, bytes], resources: Mapping[str, str]
) -> dict[str, Any]:
    book_table = "\n\n| Book | Name | Chapters |\n|---|---|---|\n" + "\n".join(
        f"| {book} | {name} | {chapters} |"
        for book, (name, chapters) in enumerate(
            zip(BOOK_NAMES, BOOK_CHAPTER_COUNTS, strict=True), 1
        )
    )
    definitions = {
        "id": (
            schemas["Topic"]["properties"]["id"],
            "Exact topic id from topics.json. Aliases and display names are not URL ids.",
        ),
        "book": (
            schemas["Book"]["properties"]["book"],
            "Book number in the 66-book Protestant canon, without leading zeros." + book_table,
        ),
        "chapter": (
            schemas["Chapter"]["properties"]["chapter"],
            "Chapter number without leading zeros. Must not exceed the selected book's chapter "
            "count (see the book parameter table); 150 is only the maximum across all books.",
        ),
        "locale": (
            schemas["Locale"]["properties"]["locale"],
            "Exact lowercase locale code from locales.json, such as en or zh-hant. "
            "Unsupported locales do not fall back automatically.",
        ),
    }
    parameters = {
        name: {"name": name, "in": "path", "required": True, "schema": schema, "description": text}
        for name, (schema, text) in definitions.items()
    }
    topics = json.loads(files[resources["topics"]])["topics"]
    book, chapter = 1, 1
    if topics:
        identifier = topics[0]["id"]
        parameters["id"]["example"] = identifier
        topic = json.loads(files[resources["topic"].format(id=identifier)])
        if topic["verses"]:
            book, chapter, _ = topic["verses"][0]
    parameters["book"]["example"] = book
    parameters["chapter"]["example"] = chapter
    parameters["locale"]["example"] = ENGLISH_LOCALE
    return parameters


def _example(
    resource: str, path: str, files: Mapping[str, bytes], parameters: Mapping[str, Any]
) -> dict[str, Any] | None:
    if resource == "openapi":
        return None  # Embedding the document within itself would recurse.
    if "{" not in path:
        # Avoid copying aggregate payloads, a previous catalogue version, or
        # the checksum of this very document into its own bytes.
        return {"summary": "Complete published response", "externalValue": "./" + path}
    values = {
        name: parameter["example"]
        for name, parameter in parameters.items()
        if "example" in parameter
    }
    if resource == "topic" and "id" not in values:
        return None  # An empty catalogue has no real topic to use as an example.
    relative = path.format(**values)
    content = files[relative]
    if len(content) > 16384:
        return {"summary": f"Complete response from {relative}", "externalValue": "./" + relative}
    return {"summary": f"Complete response from {relative}", "value": json.loads(content)}
