from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bookmark_builder.build import (
    RESOURCES,
    PublishedState,
    catalog_checksum,
    catalog_version,
    next_catalog_version,
    read_published_state,
    render_api,
    stale_paths,
    write_tree,
)
from bookmark_builder.canon import CHAPTER_COUNT
from bookmark_builder.model import CatalogError
from bookmark_builder.sources import load_catalog, render_sources, save_catalog
from tests.helpers import sample_catalog

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


class SourceRoundTripTests(unittest.TestCase):
    def test_save_and_load_round_trip(self) -> None:
        catalog = sample_catalog()
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            changed = save_catalog(data, catalog)
            self.assertIn("topics.json", changed)
            self.assertIn("links/grace.json", changed)
            self.assertIn("locales/fr.json", changed)
            loaded = load_catalog(data)
            self.assertEqual(render_sources(loaded), render_sources(catalog))
            self.assertEqual(save_catalog(data, loaded), [])
            # Deleting removes the link file, the locale entries and the topic itself.
            loaded.delete_topic("grace")
            changed = save_catalog(data, loaded)
            self.assertIn("links/grace.json", changed)
            self.assertIn("locales/de.json", changed)
            self.assertFalse((data / "links" / "grace.json").exists())
            reloaded = load_catalog(data)
            self.assertEqual(list(reloaded.topics), ["gods-judgment"])
            self.assertEqual(reloaded.locales["de"].topics, {})

    def test_load_rejects_defects(self) -> None:
        catalog = sample_catalog()
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            save_catalog(data, catalog)
            links = data / "links" / "grace.json"
            document = json.loads(links.read_text())
            document["verses"].append(document["verses"][0])
            links.write_text(json.dumps(document))
            with self.assertRaisesRegex(CatalogError, "ascending"):
                load_catalog(data)
            links.write_text(json.dumps({"schema_version": 1, "topic": "ghost", "verses": []}))
            with self.assertRaisesRegex(CatalogError, "must be ghost.json"):
                load_catalog(data)
            links.unlink()
            (data / "links" / "ghost.json").write_text(
                json.dumps({"schema_version": 1, "topic": "ghost", "verses": []})
            )
            with self.assertRaisesRegex(CatalogError, "unknown topic"):
                load_catalog(data)
            (data / "links" / "ghost.json").unlink()
            topics = json.loads((data / "topics.json").read_text())
            topics["catalog_version"] = 1
            (data / "topics.json").write_text(json.dumps(topics))
            with self.assertRaisesRegex(CatalogError, "unsupported catalog_version"):
                load_catalog(data)
            (data / "topics.json").write_text("{not json")
            with self.assertRaisesRegex(CatalogError, "not valid"):
                load_catalog(data)
            (data / "topics.json").unlink()
            with self.assertRaisesRegex(CatalogError, "missing"):
                load_catalog(data)

    def test_missing_links_file_means_no_verses(self) -> None:
        catalog = sample_catalog()
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            save_catalog(data, catalog)
            (data / "links" / "grace.json").unlink()
            loaded = load_catalog(data)
            self.assertEqual(loaded.sorted_verses("grace"), [])
            # Normalising writes the empty file back.
            self.assertIn("links/grace.json", save_catalog(data, loaded))

    def test_repository_sources_load_and_are_normalized(self) -> None:
        catalog = load_catalog(REPOSITORY_ROOT / "data")
        self.assertGreaterEqual(len(catalog.topics), 61)
        self.assertGreaterEqual(catalog.link_count(), 2155)
        self.assertGreaterEqual(len(catalog.locales), 50)
        for locale in catalog.sorted_locales():
            self.assertIsNotNone(locale.name, locale.code)
        for relative, content in render_sources(catalog).items():
            self.assertEqual((REPOSITORY_ROOT / "data" / relative).read_bytes(), content, relative)


class BuildTests(unittest.TestCase):
    def test_render_is_deterministic_and_complete(self) -> None:
        catalog = sample_catalog()
        files = render_api(catalog)
        self.assertEqual(files, render_api(sample_catalog()))
        # 66 book files + every canonical chapter + top-level documents + topics + locales.
        expected = 66 + CHAPTER_COUNT + 6 + 2 + 3
        self.assertEqual(len(files), expected)
        index = json.loads(files["index.json"])
        self.assertEqual(index["catalog_version"], 1)
        self.assertEqual(index["counts"], {"topics": 2, "verses": 5, "locales": 3})
        self.assertEqual(index["checksum"], catalog_checksum(files))
        self.assertEqual(index["resources"], dict(RESOURCES))
        self.assertEqual(index["locales"], ["de", "en", "fr"])
        everything = json.loads(files["all.json"])
        self.assertEqual(set(everything), {"schema_version", "topics", "locales"})
        self.assertEqual(everything["locales"]["fr"]["topics"]["grace"], "Grâce")
        catalog_document = json.loads(files["catalog.json"])
        self.assertEqual(set(catalog_document), {"schema_version", "topics"})
        self.assertEqual(catalog_document["topics"], everything["topics"])
        topics = json.loads(files["topics.json"])
        self.assertEqual(
            topics["topics"][1],
            {
                "id": "grace",
                "name": "Grace",
                "color": "#bbf7d0",
                "aliases": [],
                "default": True,
                "verses": 3,
            },
        )
        topic = json.loads(files["topics/grace.json"])
        self.assertEqual(topic["verses"], [[45, 5, 20], [49, 2, 8], [49, 2, 9]])
        self.assertEqual(topic["names"], {"de": "Gnade", "en": "Grace", "fr": "Grâce"})
        chapter = json.loads(files["verses/49/2.json"])
        self.assertEqual(
            chapter,
            {
                "schema_version": 1,
                "book": 49,
                "chapter": 2,
                "verses": {"8": ["grace"], "9": ["grace"]},
            },
        )
        book = json.loads(files["verses/45.json"])
        self.assertEqual(book["chapters"], {"2": {"5": ["gods-judgment"]}, "5": {"20": ["grace"]}})
        empty = json.loads(files["verses/1/1.json"])
        self.assertEqual(empty["verses"], {})
        english = json.loads(files["locales/en.json"])
        self.assertEqual(english["topics"], {"gods-judgment": "God's Judgment", "grace": "Grace"})
        locales = json.loads(files["locales.json"])
        self.assertEqual(locales["locales"][0], {"code": "de", "name": "German", "topics": 1})
        checksums = json.loads(files["checksums.json"])
        self.assertEqual(set(checksums["files"]), set(files) - {"checksums.json"})
        self.assertNotIn("retired.json", files)

    def test_version_follows_the_published_checksum(self) -> None:
        catalog = sample_catalog()
        files = render_api(catalog)
        checksum = catalog_checksum(files)
        self.assertEqual(next_catalog_version(None, checksum), 1)
        same = PublishedState(catalog_version=7, checksum=checksum)
        self.assertEqual(catalog_version(render_api(catalog, previous=same)), 7)
        other = PublishedState(catalog_version=7, checksum="0" * 64)
        self.assertEqual(catalog_version(render_api(catalog, previous=other)), 8)
        # Only index.json carries the version; content documents are identical.
        unchanged = render_api(catalog, previous=other)
        for relative in files:
            if relative not in ("index.json", "checksums.json"):
                self.assertEqual(unchanged[relative], files[relative], relative)
        # A translation-only change moves the checksum too.
        catalog.set_locale_names("de", {"grace": "Gnade Gottes"})
        self.assertNotEqual(catalog_checksum(render_api(catalog)), checksum)

    def test_read_published_state(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            index = Path(folder) / "index.json"
            self.assertIsNone(read_published_state(index))
            # A present but damaged index must stop the build, never reset the version.
            for damaged in (
                "{not json",
                json.dumps([]),
                json.dumps({"catalog_version": 0, "checksum": "a" * 64}),
                json.dumps({"catalog_version": True, "checksum": "a" * 64}),
                json.dumps({"catalog_version": 3, "checksum": "short"}),
            ):
                index.write_text(damaged)
                with self.assertRaises(CatalogError, msg=damaged):
                    read_published_state(index)
            index.write_text(json.dumps({"catalog_version": 3, "checksum": "a" * 64}))
            self.assertEqual(
                read_published_state(index), PublishedState(catalog_version=3, checksum="a" * 64)
            )

    def test_deleted_topic_leaves_no_trace(self) -> None:
        catalog = sample_catalog()
        catalog.delete_topic("grace")
        files = render_api(catalog)
        self.assertNotIn("topics/grace.json", files)
        for relative, content in files.items():
            self.assertNotIn(b"grace", content, relative)

    def test_write_tree_and_stale_paths(self) -> None:
        catalog = sample_catalog()
        files = render_api(catalog)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "v1"
            write_tree(root, files)
            self.assertEqual(stale_paths(root, files), [])
            # The tree is readable by other users, unlike a raw mkdtemp directory.
            self.assertEqual(root.stat().st_mode & 0o077, (root / "topics").stat().st_mode & 0o077)
            (root / "extra.json").write_text("{}")
            (root / "index.json").write_text("{}")
            self.assertEqual(stale_paths(root, files), ["extra.json", "index.json"])
            write_tree(root, files)
            self.assertEqual(stale_paths(root, files), [])
            self.assertFalse((root / "extra.json").exists())

    def test_repository_build_is_idempotent(self) -> None:
        catalog = load_catalog(REPOSITORY_ROOT / "data")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "v1"
            write_tree(root, render_api(catalog))
            first = read_published_state(root / "index.json")
            assert first is not None
            self.assertEqual(first.catalog_version, 1)
            again = render_api(catalog, previous=first)
            self.assertEqual(stale_paths(root, again), [])
