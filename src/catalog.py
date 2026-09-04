"""Catalogue model and the validation rules every writer must obey.

The rules deliberately match the getbible/robot contribution pipeline so a
bundle accepted there is accepted here unchanged: stable slug identifiers,
English canonical names, lowercase six-digit hex colours, bounded alias lists
and translation-independent Protestant-canon verse coordinates.

The catalogue is exactly what the source files say. Deleting a topic removes
it together with its verse links and translated names; git history is the
only memory of what existed before.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from canon import BOOK_CHAPTER_COUNTS, BOOK_COUNT, MAX_VERSE, is_canonical_coordinate

MAX_TOPICS = 1000
MAX_LINKS = 100_000
MAX_LOCALES = 500
MAX_TOPIC_ID = 80
MAX_TOPIC_NAME = 80
MAX_ALIASES = 20
MAX_TRANSLATED_NAME = 120
MAX_LOCALE_NAME = 80
MAX_VERSES_PER_REQUEST = 10_000

TOPIC_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
COLOR_RE = re.compile(r"#[0-9a-f]{6}\Z")
ENGLISH_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 &'():?-]*[A-Za-z0-9)]\Z")
LOCALE_RE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*\Z")
ENGLISH_LOCALE = "en"

Coordinate = tuple[int, int, int]


class CatalogError(ValueError):
    """A source document or a requested change violates the catalogue rules."""


@dataclass(frozen=True)
class Topic:
    id: str
    name: str
    color: str
    aliases: tuple[str, ...] = ()
    default: bool = False


@dataclass
class Locale:
    code: str
    name: str | None
    topics: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Field validators
# --------------------------------------------------------------------------- #


def topic_id(value: object, label: str = "topic id") -> str:
    text = _text(value, label, MAX_TOPIC_ID)
    if TOPIC_ID_RE.fullmatch(text) is None:
        raise CatalogError(
            f"{label} {text!r} must be a lowercase slug of letters, digits and single hyphens."
        )
    return text


def english_name(value: object, label: str = "name") -> str:
    text = _text(value, label, MAX_TOPIC_NAME)
    if ENGLISH_NAME_RE.fullmatch(text) is None or "  " in text:
        raise CatalogError(
            f"{label} {text!r} must be a plain English phrase "
            "(letters, digits, spaces and & ' ( ) : ? -)."
        )
    return text


def color(value: object, label: str = "color") -> str:
    text = _text(value, label, 7)
    lowered = text.lower()
    if COLOR_RE.fullmatch(lowered) is None:
        raise CatalogError(f"{label} {text!r} must be a six-digit hex colour such as #93c5fd.")
    return lowered


def aliases(value: object, label: str = "aliases") -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CatalogError(f"{label} must be an array of English names.")
    if len(value) > MAX_ALIASES:
        raise CatalogError(f"{label} may contain at most {MAX_ALIASES} entries.")
    unique: dict[str, str] = {}
    for item in sorted(english_name(entry, f"{label} entry") for entry in value):
        unique.setdefault(fold_name(item), item)
    return tuple(sorted(unique.values()))


def locale_code(value: object, label: str = "locale") -> str:
    text = _text(value, label, 16)
    if LOCALE_RE.fullmatch(text) is None:
        raise CatalogError(
            f"{label} {text!r} must be a lowercase BCP 47 style tag such as fr or zh-hant."
        )
    return text


def translated_name(value: object, label: str = "translated name") -> str:
    text = _text(value, label, MAX_TRANSLATED_NAME)
    if any(unicodedata.category(char)[0] == "C" for char in text):
        raise CatalogError(f"{label} must not contain control characters.")
    return unicodedata.normalize("NFC", text)


def locale_name(value: object, label: str = "locale name") -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and len(value) > MAX_LOCALE_NAME:
        raise CatalogError(f"{label} may contain at most {MAX_LOCALE_NAME} characters.")
    return translated_name(value, label)


def coordinate(value: object, label: str = "verse") -> Coordinate:
    """Accept ``[book, chapter, verse]`` or ``{"book", "chapter", "verse"}``."""
    if isinstance(value, Mapping):
        if set(value) != {"book", "chapter", "verse"}:
            raise CatalogError(f"{label} must contain exactly book, chapter and verse.")
        parts: tuple[object, object, object] = (value["book"], value["chapter"], value["verse"])
    elif isinstance(value, list | tuple) and len(value) == 3:
        parts = (value[0], value[1], value[2])
    else:
        raise CatalogError(f"{label} must be a [book, chapter, verse] triple.")
    book, chapter, verse = parts
    if not is_canonical_coordinate(book, chapter, verse):
        raise CatalogError(
            f"{label} {list(parts)!r} is outside the {BOOK_COUNT}-book canon "
            f"(chapters per book are fixed, verses are 1..{MAX_VERSE})."
        )
    assert isinstance(book, int) and isinstance(chapter, int) and isinstance(verse, int)
    return (book, chapter, verse)


def coordinates(value: object, label: str = "verses") -> list[Coordinate]:
    if not isinstance(value, list):
        raise CatalogError(f"{label} must be an array of verse coordinates.")
    if len(value) > MAX_VERSES_PER_REQUEST:
        raise CatalogError(f"{label} may contain at most {MAX_VERSES_PER_REQUEST} coordinates.")
    seen: dict[Coordinate, None] = {}
    for index, item in enumerate(value):
        seen.setdefault(coordinate(item, f"{label}[{index}]"), None)
    return list(seen)


def fold_name(value: str) -> str:
    """Case and whitespace insensitive key used for English name uniqueness."""
    return " ".join(value.lower().split())


def slugify(name: str) -> str:
    """Derive the stable identifier the robot derives for a new English topic."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"['’]", "", text.lower())  # noqa: RUF001 - apostrophes are dropped
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not text:
        raise CatalogError(f"A stable identifier cannot be derived from {name!r}.")
    return text[:MAX_TOPIC_ID].rstrip("-")


def exact_keys(value: object, expected: Iterable[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CatalogError(f"{label} must be a JSON object.")
    expected_set = set(expected)
    if set(value) != expected_set:
        missing = sorted(expected_set - set(value))
        extra = sorted(set(value) - expected_set)
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if extra:
            detail.append(f"unsupported {', '.join(extra)}")
        raise CatalogError(f"{label} has {'; '.join(detail)}.")
    return value


def allowed_keys(value: object, allowed: Iterable[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CatalogError(f"{label} must be a JSON object.")
    extra = sorted(set(value) - set(allowed))
    if extra:
        raise CatalogError(f"{label} has unsupported fields: {', '.join(extra)}.")
    return value


def _text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise CatalogError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise CatalogError(f"{label} must not be empty.")
    if len(text) > maximum:
        raise CatalogError(f"{label} may contain at most {maximum} characters.")
    return text


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #


@dataclass
class Catalog:
    """The complete canonical state: topics, verse links and translated names."""

    topics: dict[str, Topic] = field(default_factory=dict)
    links: dict[str, set[Coordinate]] = field(default_factory=dict)
    locales: dict[str, Locale] = field(default_factory=dict)

    # -- views ------------------------------------------------------------- #

    def sorted_topics(self) -> list[Topic]:
        return [self.topics[key] for key in sorted(self.topics)]

    def sorted_verses(self, topic_id: str) -> list[Coordinate]:
        return sorted(self.links.get(topic_id, set()))

    def sorted_locales(self) -> list[Locale]:
        return [self.locales[key] for key in sorted(self.locales)]

    def link_count(self) -> int:
        return sum(len(verses) for verses in self.links.values())

    def taken_names(self) -> dict[str, str]:
        names: dict[str, str] = {}
        for topic in self.topics.values():
            for candidate in (topic.name, *topic.aliases):
                names[fold_name(candidate)] = topic.id
        return names

    def require_topic(self, topic_id: str) -> Topic:
        topic = self.topics.get(topic_id)
        if topic is None:
            raise CatalogError(f"Topic {topic_id!r} does not exist.")
        return topic

    # -- invariants -------------------------------------------------------- #

    def validate(self) -> None:
        if len(self.topics) > MAX_TOPICS:
            raise CatalogError(f"The catalogue may contain at most {MAX_TOPICS} topics.")
        if len(self.locales) > MAX_LOCALES:
            raise CatalogError(f"The catalogue may contain at most {MAX_LOCALES} locales.")
        names: dict[str, str] = {}
        for key, topic in self.topics.items():
            if key != topic.id or topic_id(topic.id) != key:
                raise CatalogError(f"Topic key {key!r} does not match its id.")
            english_name(topic.name, f"topic {key} name")
            color(topic.color, f"topic {key} color")
            if topic.color != topic.color.lower():
                raise CatalogError(f"topic {key} color must be lowercase.")
            if aliases(list(topic.aliases)) != topic.aliases:
                raise CatalogError(f"topic {key} aliases must be sorted and unique.")
            own: set[str] = set()
            for candidate in (topic.name, *topic.aliases):
                folded = fold_name(candidate)
                if folded in own:
                    raise CatalogError(
                        f"topic {key} lists {candidate!r} more than once among its name and aliases."
                    )
                own.add(folded)
                owner = names.get(folded)
                if owner is not None and owner != key:
                    raise CatalogError(
                        f"English name {candidate!r} is used by both {owner} and {key}."
                    )
                names[folded] = key
        total = 0
        for key, verses in self.links.items():
            if key not in self.topics:
                raise CatalogError(f"Verse links refer to unknown topic {key!r}.")
            for verse in verses:
                coordinate(list(verse), f"topic {key} verse")
            total += len(verses)
        if total > MAX_LINKS:
            raise CatalogError(f"The catalogue may contain at most {MAX_LINKS} verse links.")
        for key, locale in self.locales.items():
            if key != locale.code or locale_code(locale.code) != key:
                raise CatalogError(f"Locale key {key!r} does not match its code.")
            if key == ENGLISH_LOCALE:
                raise CatalogError("English names live on the topics themselves, not in a locale.")
            locale_name(locale.name, f"locale {key} name")
            for topic_key, name in locale.topics.items():
                if topic_key not in self.topics:
                    raise CatalogError(f"locale {key} names unknown topic {topic_key!r}.")
                translated_name(name, f"locale {key} name for {topic_key}")

    # -- mutations --------------------------------------------------------- #

    def create_topic(
        self,
        *,
        name: object,
        color_value: object,
        identifier: object = None,
        alias_values: object = None,
        default: object = False,
        verses: object = None,
        names: object = None,
    ) -> Topic:
        canonical_name = english_name(name)
        new_id = topic_id(identifier) if identifier is not None else slugify(canonical_name)
        if new_id in self.topics:
            raise CatalogError(f"Topic {new_id!r} already exists.")
        if len(self.topics) >= MAX_TOPICS:
            raise CatalogError(f"The catalogue may contain at most {MAX_TOPICS} topics.")
        if not isinstance(default, bool):
            raise CatalogError("default must be true or false.")
        topic = Topic(
            id=new_id,
            name=canonical_name,
            color=color(color_value),
            aliases=tuple(
                alias
                for alias in aliases(alias_values)
                if fold_name(alias) != fold_name(canonical_name)
            ),
            default=default,
        )
        self._assert_names_free(topic, exclude=None)
        self.topics[new_id] = topic
        self.links[new_id] = set()
        if verses is not None:
            self.add_verses(new_id, verses)
        if names is not None:
            self._set_topic_names(new_id, names)
        return topic

    def update_topic(
        self,
        identifier: str,
        *,
        name: object = None,
        color_value: object = None,
        alias_values: object = None,
        default: object = None,
    ) -> Topic:
        current = self.require_topic(identifier)
        updated = current
        if name is not None:
            new_name = english_name(name)
            if fold_name(new_name) != fold_name(current.name):
                # The previous wording stays valid as an alias so stored mappings and
                # existing translations keep resolving (robot permanence rule).
                kept = tuple(sorted({*current.aliases, current.name}))
                updated = replace(updated, name=new_name, aliases=kept)
            else:
                updated = replace(updated, name=new_name)
        if color_value is not None:
            updated = replace(updated, color=color(color_value))
        if alias_values is not None:
            updated = replace(updated, aliases=aliases(alias_values))
        if default is not None:
            if not isinstance(default, bool):
                raise CatalogError("default must be true or false.")
            updated = replace(updated, default=default)
        updated = replace(
            updated,
            aliases=tuple(a for a in updated.aliases if fold_name(a) != fold_name(updated.name)),
        )
        self._assert_names_free(updated, exclude=identifier)
        self.topics[identifier] = updated
        return updated

    def delete_topic(self, identifier: str) -> Topic:
        """Remove a topic completely: its metadata, verse links and translated names."""
        current = self.require_topic(identifier)
        del self.topics[identifier]
        self.links.pop(identifier, None)
        for locale in self.locales.values():
            locale.topics.pop(identifier, None)
        return current

    def add_verses(self, identifier: str, verses: object) -> int:
        self.require_topic(identifier)
        wanted = coordinates(verses)
        existing = self.links.setdefault(identifier, set())
        if self.link_count() + len(wanted) > MAX_LINKS:
            raise CatalogError(f"The catalogue may contain at most {MAX_LINKS} verse links.")
        before = len(existing)
        existing.update(wanted)
        return len(existing) - before

    def remove_verses(self, identifier: str, verses: object) -> int:
        self.require_topic(identifier)
        wanted = coordinates(verses)
        existing = self.links.setdefault(identifier, set())
        before = len(existing)
        existing.difference_update(wanted)
        return before - len(existing)

    def replace_verses(self, identifier: str, verses: object) -> tuple[int, int]:
        self.require_topic(identifier)
        wanted = set(coordinates(verses))
        existing = self.links.setdefault(identifier, set())
        added = len(wanted - existing)
        removed = len(existing - wanted)
        if self.link_count() - len(existing) + len(wanted) > MAX_LINKS:
            raise CatalogError(f"The catalogue may contain at most {MAX_LINKS} verse links.")
        self.links[identifier] = wanted
        return added, removed

    def set_locale_names(
        self, code: object, names: object, *, name: object = None, replace_all: bool = False
    ) -> int:
        locale_key = locale_code(code)
        if locale_key == ENGLISH_LOCALE:
            raise CatalogError("English names are edited on the topic, not through a locale.")
        if not isinstance(names, Mapping):
            raise CatalogError("topics must be an object of topic id to translated name.")
        validated = {
            self.require_topic(topic_id(key)).id: translated_name(value, f"name for {key}")
            for key, value in names.items()
        }
        locale = self.locales.get(locale_key)
        if locale is None:
            if len(self.locales) >= MAX_LOCALES:
                raise CatalogError(f"The catalogue may contain at most {MAX_LOCALES} locales.")
            locale = Locale(code=locale_key, name=None)
            self.locales[locale_key] = locale
        if name is not None:
            locale.name = locale_name(name)
        before = dict(locale.topics)
        after = dict(validated) if replace_all else {**before, **validated}
        locale.topics = after
        return sum(1 for key in set(before) | set(after) if before.get(key) != after.get(key))

    def delete_locale_name(self, code: object, identifier: object) -> bool:
        locale_key = locale_code(code)
        key = topic_id(identifier)
        locale = self.locales.get(locale_key)
        if locale is None or key not in locale.topics:
            return False
        del locale.topics[key]
        return True

    def delete_locale(self, code: object) -> bool:
        locale_key = locale_code(code)
        return self.locales.pop(locale_key, None) is not None

    # -- helpers ----------------------------------------------------------- #

    def _set_topic_names(self, identifier: str, names: object) -> None:
        if not isinstance(names, Mapping):
            raise CatalogError("names must be an object of locale to translated name.")
        for code, value in names.items():
            self.set_locale_names(code, {identifier: value})

    def _assert_names_free(self, topic: Topic, *, exclude: str | None) -> None:
        taken = self.taken_names()
        for candidate in (topic.name, *topic.aliases):
            owner = taken.get(fold_name(candidate))
            if owner is not None and owner != exclude:
                raise CatalogError(
                    f"English name {candidate!r} is already used by topic {owner!r}."
                )


def copy_catalog(catalog: Catalog) -> Catalog:
    return Catalog(
        topics=dict(catalog.topics),
        links={key: set(value) for key, value in catalog.links.items()},
        locales={
            key: Locale(code=value.code, name=value.name, topics=dict(value.topics))
            for key, value in catalog.locales.items()
        },
    )


__all__ = [
    "BOOK_CHAPTER_COUNTS",
    "Catalog",
    "CatalogError",
    "Coordinate",
    "Locale",
    "Topic",
    "aliases",
    "allowed_keys",
    "color",
    "coordinate",
    "coordinates",
    "copy_catalog",
    "english_name",
    "exact_keys",
    "fold_name",
    "locale_code",
    "locale_name",
    "slugify",
    "topic_id",
    "translated_name",
]
