"""Load and save the canonical source documents under ``data/``.

Layout::

    data/topics.json            topic metadata
    data/links/<topic>.json     sorted [book, chapter, verse] triples per topic
    data/locales/<locale>.json  translated topic names per locale

Every document is rendered deterministically so a round trip through
``load_catalog``/``save_catalog`` is byte identical. The layout is one file
per topic and per locale on purpose: a contributor, the robot or the app can
change one topic through the GitHub contents API without touching anything
else, and a review diff shows exactly which topic or language moved.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from catalog import (
    Catalog,
    CatalogError,
    Locale,
    Topic,
    aliases,
    color,
    coordinate,
    english_name,
    exact_keys,
    locale_code,
    locale_name,
    topic_id,
    translated_name,
)
from jsonfmt import dump_bytes
from meta import SCHEMA_VERSION

TOPICS_FILE = "topics.json"
LINKS_DIR = "links"
LOCALES_DIR = "locales"
MAX_SOURCE_BYTES = 8 * 1024 * 1024


def load_catalog(data_dir: Path) -> Catalog:
    """Parse and validate every source document, raising CatalogError on any defect."""
    topics_doc = exact_keys(
        _read_json(data_dir / TOPICS_FILE), ("schema_version", "topics"), TOPICS_FILE
    )
    _schema(topics_doc, TOPICS_FILE)
    catalog = Catalog()
    if not isinstance(topics_doc["topics"], list):
        raise CatalogError(f"{TOPICS_FILE}.topics must be an array.")
    for index, raw in enumerate(topics_doc["topics"]):
        label = f"{TOPICS_FILE}.topics[{index}]"
        item = exact_keys(raw, ("id", "name", "color", "aliases", "default"), label)
        if not isinstance(item["default"], bool):
            raise CatalogError(f"{label}.default must be true or false.")
        topic = Topic(
            id=topic_id(item["id"], f"{label}.id"),
            name=english_name(item["name"], f"{label}.name"),
            color=color(item["color"], f"{label}.color"),
            aliases=aliases(item["aliases"], f"{label}.aliases"),
            default=item["default"],
        )
        if topic.id in catalog.topics:
            raise CatalogError(f"{TOPICS_FILE} defines topic {topic.id!r} twice.")
        catalog.topics[topic.id] = topic
        catalog.links[topic.id] = set()

    links_dir = data_dir / LINKS_DIR
    for path in sorted(links_dir.glob("*.json")) if links_dir.is_dir() else []:
        label = f"{LINKS_DIR}/{path.name}"
        doc = exact_keys(_read_json(path), ("schema_version", "topic", "verses"), label)
        _schema(doc, label)
        key = topic_id(doc["topic"], f"{label}.topic")
        if path.stem != key:
            raise CatalogError(f"{label} names topic {key!r}; the file must be {key}.json.")
        if key not in catalog.topics:
            raise CatalogError(f"{label} links verses to unknown topic {key!r}.")
        if not isinstance(doc["verses"], list):
            raise CatalogError(f"{label}.verses must be an array.")
        verses = catalog.links[key]
        previous = None
        for index, raw in enumerate(doc["verses"]):
            triple = coordinate(raw, f"{label}.verses[{index}]")
            if previous is not None and triple <= previous:
                raise CatalogError(f"{label}.verses must be strictly ascending without duplicates.")
            previous = triple
            verses.add(triple)

    locales_dir = data_dir / LOCALES_DIR
    for path in sorted(locales_dir.glob("*.json")) if locales_dir.is_dir() else []:
        label = f"{LOCALES_DIR}/{path.name}"
        raw_doc = _read_json(path)
        if not isinstance(raw_doc, Mapping):
            raise CatalogError(f"{label} must be a JSON object.")
        expected = ["schema_version", "locale", "topics"] + (["name"] if "name" in raw_doc else [])
        doc = exact_keys(raw_doc, expected, label)
        _schema(doc, label)
        code = locale_code(doc["locale"], f"{label}.locale")
        if path.stem != code:
            raise CatalogError(f"{label} declares locale {code!r}; the file must be {code}.json.")
        if not isinstance(doc["topics"], Mapping):
            raise CatalogError(f"{label}.topics must be an object.")
        locale = Locale(code=code, name=locale_name(doc.get("name"), f"{label}.name"))
        keys = list(doc["topics"])
        if keys != sorted(keys):
            raise CatalogError(f"{label}.topics must be sorted by topic id.")
        for key, value in doc["topics"].items():
            topic_key = topic_id(key, f"{label}.topics key")
            if topic_key not in catalog.topics:
                raise CatalogError(f"{label} translates unknown topic {topic_key!r}.")
            locale.topics[topic_key] = translated_name(value, f"{label}.topics.{topic_key}")
        catalog.locales[code] = locale

    catalog.validate()
    return catalog


def render_sources(catalog: Catalog) -> dict[str, bytes]:
    """Return every source document as ``relative path -> bytes``."""
    catalog.validate()
    files: dict[str, bytes] = {}
    files[TOPICS_FILE] = dump_bytes(
        {
            "schema_version": SCHEMA_VERSION,
            "topics": [
                {
                    "id": topic.id,
                    "name": topic.name,
                    "color": topic.color,
                    "aliases": list(topic.aliases),
                    "default": topic.default,
                }
                for topic in catalog.sorted_topics()
            ],
        }
    )
    for topic in catalog.sorted_topics():
        files[f"{LINKS_DIR}/{topic.id}.json"] = dump_bytes(
            {
                "schema_version": SCHEMA_VERSION,
                "topic": topic.id,
                "verses": [list(verse) for verse in catalog.sorted_verses(topic.id)],
            }
        )
    for locale in catalog.sorted_locales():
        document: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "locale": locale.code}
        if locale.name is not None:
            document["name"] = locale.name
        document["topics"] = {key: locale.topics[key] for key in sorted(locale.topics)}
        files[f"{LOCALES_DIR}/{locale.code}.json"] = dump_bytes(document)
    return files


def save_catalog(data_dir: Path, catalog: Catalog) -> list[str]:
    """Write the sources, removing stale link/locale files. Returns changed paths."""
    files = render_sources(catalog)
    changed: list[str] = []
    for relative, content in files.items():
        path = data_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() == content:
            continue
        _atomic_write(path, content)
        changed.append(relative)
    for directory in (LINKS_DIR, LOCALES_DIR):
        folder = data_dir / directory
        if not folder.is_dir():
            continue
        for path in folder.glob("*.json"):
            relative = f"{directory}/{path.name}"
            if relative not in files:
                path.unlink()
                changed.append(relative)
    return sorted(changed)


def _read_json(path: Path) -> Any:
    try:
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise CatalogError(f"{path.name} exceeds {MAX_SOURCE_BYTES} bytes.")
        return json.loads(path.read_text("utf-8"))
    except FileNotFoundError as error:
        raise CatalogError(f"{path} is missing.") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogError(f"{path.name} is not valid UTF-8 JSON: {error}") from error


def _schema(document: Mapping[str, Any], label: str) -> None:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise CatalogError(f"{label} has an unsupported schema_version.")


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with open(temporary, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
