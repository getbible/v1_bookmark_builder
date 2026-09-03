"""Render the static JSON API tree from a validated catalogue.

Every document is a pure function of the sources: the same ``data/`` always
produces the same bytes, so a rebuild without a data change is a no-op for the
downstream repository and nginx can serve the files with plain ETags.

``all.json`` is the reference document. It holds the complete content (every
topic with its verses, every locale) and nothing else, and its SHA-256 is the
catalogue ``checksum`` quoted by ``index.json``. The ``catalog_version`` in
``index.json`` is not stored in the sources: the builder reads the previously
published ``index.json`` and increments the version whenever the checksum
changed, so contributors never have to bump a number by hand.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .canon import BOOK_CHAPTER_COUNTS, BOOK_COUNT
from .jsonfmt import dump_bytes
from .model import ENGLISH_LOCALE, Catalog, CatalogError, Topic

API_VERSION = "v1"
RESOURCES: Mapping[str, str] = {
    "index": "index.json",
    "all": "all.json",
    "catalog": "catalog.json",
    "topics": "topics.json",
    "topic": "topics/{id}.json",
    "book": "verses/{book}.json",
    "chapter": "verses/{book}/{chapter}.json",
    "locales": "locales.json",
    "locale": "locales/{locale}.json",
    "checksums": "checksums.json",
}
MAX_CATALOG_VERSION = 2**53


@dataclass(frozen=True)
class PublishedState:
    """What the previously published ``index.json`` said, if anything."""

    catalog_version: int
    checksum: str


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_published_state(index_path: Path) -> PublishedState | None:
    """Return the version and checksum from the published ``index.json``.

    A missing file means "never published" and the next build starts at
    version 1. A file that exists but cannot be read or does not carry a valid
    version and checksum raises instead: the catalogue version must never move
    backwards, so a damaged downstream ``index.json`` stops the build until a
    person looks at it.
    """
    try:
        text = index_path.read_text("utf-8")
    except FileNotFoundError:
        return None
    except OSError as error:
        raise CatalogError(f"{index_path} cannot be read: {error}") from error
    try:
        document = json.loads(text)
    except ValueError as error:
        raise CatalogError(f"{index_path} is not valid JSON: {error}") from error
    version = document.get("catalog_version") if isinstance(document, Mapping) else None
    checksum = document.get("checksum") if isinstance(document, Mapping) else None
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or not 1 <= version <= MAX_CATALOG_VERSION
        or not isinstance(checksum, str)
        or len(checksum) != 64
    ):
        raise CatalogError(
            f"{index_path} does not carry a valid catalog_version and checksum; "
            "refusing to reset the published version."
        )
    return PublishedState(catalog_version=version, checksum=checksum)


def next_catalog_version(previous: PublishedState | None, checksum: str) -> int:
    """Increment only when the content checksum differs from the published one."""
    if previous is None:
        return 1
    if previous.checksum == checksum:
        return previous.catalog_version
    return previous.catalog_version + 1


def render_api(catalog: Catalog, *, previous: PublishedState | None = None) -> dict[str, bytes]:
    """Return the complete API tree as ``relative path -> bytes``."""
    catalog.validate()
    files: dict[str, bytes] = {}

    topics = catalog.sorted_topics()
    topics_with_verses = [_topic_with_verses(catalog, topic) for topic in topics]

    locale_documents: dict[str, dict[str, Any]] = {
        ENGLISH_LOCALE: {
            "schema_version": SCHEMA_VERSION,
            "locale": ENGLISH_LOCALE,
            "name": "English",
            "topics": {topic.id: topic.name for topic in topics},
        }
    }
    for locale in catalog.sorted_locales():
        document: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "locale": locale.code}
        if locale.name is not None:
            document["name"] = locale.name
        document["topics"] = {key: locale.topics[key] for key in sorted(locale.topics)}
        locale_documents[locale.code] = document
    locale_codes = sorted(locale_documents)

    files[RESOURCES["all"]] = dump_bytes(
        {
            "schema_version": SCHEMA_VERSION,
            "topics": topics_with_verses,
            "locales": {code: locale_documents[code] for code in locale_codes},
        }
    )
    checksum = sha256_hex(files[RESOURCES["all"]])
    catalog_version = next_catalog_version(previous, checksum)

    files[RESOURCES["catalog"]] = dump_bytes(
        {"schema_version": SCHEMA_VERSION, "topics": topics_with_verses}
    )
    files[RESOURCES["topics"]] = dump_bytes(
        {
            "schema_version": SCHEMA_VERSION,
            "topics": [_topic_summary(catalog, topic) for topic in topics],
        }
    )
    for topic in topics:
        names = {
            code: locale_documents[code]["topics"][topic.id]
            for code in locale_codes
            if topic.id in locale_documents[code]["topics"]
        }
        files[RESOURCES["topic"].format(id=topic.id)] = dump_bytes(
            {
                "schema_version": SCHEMA_VERSION,
                **_topic_fields(topic),
                "names": names,
                "verses": [list(verse) for verse in catalog.sorted_verses(topic.id)],
            }
        )

    by_verse: dict[int, dict[int, dict[int, list[str]]]] = {}
    for topic in topics:
        for book, chapter, verse in catalog.sorted_verses(topic.id):
            by_verse.setdefault(book, {}).setdefault(chapter, {}).setdefault(verse, []).append(
                topic.id
            )
    for book in range(1, BOOK_COUNT + 1):
        chapters = by_verse.get(book, {})
        files[RESOURCES["book"].format(book=book)] = dump_bytes(
            {
                "schema_version": SCHEMA_VERSION,
                "book": book,
                "chapters": {
                    str(chapter): {str(verse): ids for verse, ids in sorted(verses.items())}
                    for chapter, verses in sorted(chapters.items())
                },
            }
        )
        for chapter in range(1, BOOK_CHAPTER_COUNTS[book - 1] + 1):
            verses = chapters.get(chapter, {})
            files[RESOURCES["chapter"].format(book=book, chapter=chapter)] = dump_bytes(
                {
                    "schema_version": SCHEMA_VERSION,
                    "book": book,
                    "chapter": chapter,
                    "verses": {str(verse): ids for verse, ids in sorted(verses.items())},
                }
            )

    for code in locale_codes:
        files[RESOURCES["locale"].format(locale=code)] = dump_bytes(locale_documents[code])
    files[RESOURCES["locales"]] = dump_bytes(
        {
            "schema_version": SCHEMA_VERSION,
            "locales": [
                {
                    "code": code,
                    "name": locale_documents[code].get("name"),
                    "topics": len(locale_documents[code]["topics"]),
                }
                for code in locale_codes
            ],
        }
    )
    files[RESOURCES["index"]] = dump_bytes(
        {
            "schema_version": SCHEMA_VERSION,
            "catalog_version": catalog_version,
            "checksum": checksum,
            "counts": {
                "topics": len(topics),
                "verses": catalog.link_count(),
                "locales": len(locale_codes),
            },
            "resources": dict(RESOURCES),
            "locales": locale_codes,
        }
    )
    files[RESOURCES["checksums"]] = dump_bytes(
        {
            "schema_version": SCHEMA_VERSION,
            "files": {path: sha256_hex(content) for path, content in sorted(files.items())},
        }
    )
    return files


def catalog_checksum(files: Mapping[str, bytes]) -> str:
    return sha256_hex(files[RESOURCES["all"]])


def catalog_version(files: Mapping[str, bytes]) -> int:
    version = json.loads(files[RESOURCES["index"]])["catalog_version"]
    assert isinstance(version, int)
    return version


def write_tree(root: Path, files: Mapping[str, bytes]) -> None:
    """Replace ``root`` with the rendered tree atomically (build beside, then swap)."""
    root = root.resolve()
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.", dir=root.parent))
    try:
        # mkdtemp creates 0700; the published tree must be readable like any
        # directory created under the caller's umask.
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(staging, 0o777 & ~umask)
        for relative, content in files.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        previous = root.with_name(f".{root.name}.previous")
        if previous.exists():
            shutil.rmtree(previous)
        if root.exists():
            os.rename(root, previous)
        os.rename(staging, root)
        if previous.exists():
            shutil.rmtree(previous)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def stale_paths(root: Path, files: Mapping[str, bytes]) -> list[str]:
    """Return paths whose bytes differ from ``files``, plus files that should not exist."""
    stale: list[str] = []
    for relative, content in files.items():
        path = root / relative
        if not path.is_file() or path.read_bytes() != content:
            stale.append(relative)
    if root.is_dir():
        for path in root.rglob("*"):
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                if relative not in files:
                    stale.append(relative)
    return sorted(stale)


def _topic_fields(topic: Topic) -> dict[str, Any]:
    return {
        "id": topic.id,
        "name": topic.name,
        "color": topic.color,
        "aliases": list(topic.aliases),
        "default": topic.default,
    }


def _topic_summary(catalog: Catalog, topic: Topic) -> dict[str, Any]:
    return {**_topic_fields(topic), "verses": len(catalog.links.get(topic.id, ()))}


def _topic_with_verses(catalog: Catalog, topic: Topic) -> dict[str, Any]:
    return {
        **_topic_fields(topic),
        "verses": [list(verse) for verse in catalog.sorted_verses(topic.id)],
    }
