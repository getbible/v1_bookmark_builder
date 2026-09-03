from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from bookmark_builder.cli import main
from bookmark_builder.sources import load_catalog, save_catalog
from tests.helpers import sample_catalog


class CliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(arguments))
        return code, out.getvalue(), err.getvalue()

    def test_validate_build_and_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            data, output = repo / "data", repo / "v1"
            save_catalog(data, sample_catalog())
            code, out, _ = self.run_cli("--data", str(data), "validate")
            self.assertEqual(code, 0)
            self.assertIn("2 topics", out)

            code, out, _ = self.run_cli(
                "--data", str(data), "build", "--output", str(output), "--check"
            )
            self.assertEqual(code, 1)
            self.assertIn("STALE", out)
            code, out, _ = self.run_cli("--data", str(data), "build", "--output", str(output))
            self.assertEqual(code, 0)
            self.assertIn("catalogue version 1", out)
            index = json.loads((output / "index.json").read_text())
            self.assertEqual(index["catalog_version"], 1)
            code, out, _ = self.run_cli(
                "--data", str(data), "build", "--output", str(output), "--check"
            )
            self.assertEqual(code, 0)
            self.assertIn("Up to date", out)
            # Rebuilding unchanged content keeps the version.
            code, out, _ = self.run_cli("--data", str(data), "build", "--output", str(output))
            self.assertIn("catalogue version 1", out)
            self.assertIn("content unchanged", out)

            bundle = repo / "bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "topics": [
                            {"id": "mercy", "name": "Mercy", "color": "#ffffff", "aliases": []}
                        ],
                        "associations": {
                            "add": [{"topic_id": "mercy", "book": 19, "chapter": 23, "verse": 6}],
                            "remove": [],
                        },
                    }
                )
            )
            code, out, _ = self.run_cli(
                "--data", str(data), "import-bundle", "--check", str(bundle)
            )
            self.assertEqual(code, 0)
            self.assertIn("would have created 1", out)
            self.assertFalse((data / "links" / "mercy.json").exists())
            code, out, _ = self.run_cli("--data", str(data), "import-bundle", str(bundle))
            self.assertEqual(code, 0)
            self.assertIn("Applied", out)
            catalog = load_catalog(data)
            self.assertEqual(catalog.sorted_verses("mercy"), [(19, 23, 6)])
            code, out, _ = self.run_cli("--data", str(data), "import-bundle", str(bundle))
            self.assertEqual(code, 0)
            self.assertIn("nothing to do", out)

            # Changed content bumps the published version on the next build.
            code, out, _ = self.run_cli("--data", str(data), "build", "--output", str(output))
            self.assertEqual(code, 0)
            self.assertIn("catalogue version 2", out)
            self.assertIn("content changed", out)
            self.assertEqual(json.loads((output / "index.json").read_text())["catalog_version"], 2)

            bad = repo / "bad.json"
            bad.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "topics": [],
                        "associations": {"add": [], "remove": []},
                        "note": "x",
                    }
                )
            )
            code, _, err = self.run_cli("--data", str(data), "import-bundle", str(bad))
            self.assertEqual(code, 1)
            self.assertIn("error:", err)

    def test_normalize_rewrites_sources(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / "data"
            save_catalog(data, sample_catalog())
            code, out, _ = self.run_cli("--data", str(data), "normalize")
            self.assertEqual(code, 0)
            self.assertIn("already in canonical form", out)
            links = data / "links" / "grace.json"
            links.write_text(json.dumps(json.loads(links.read_text())))
            code, out, _ = self.run_cli("--data", str(data), "normalize")
            self.assertEqual(code, 0)
            self.assertIn("links/grace.json", out)
            self.assertTrue(links.read_text().endswith("]\n}\n"))

    def test_invalid_sources_report_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / "data"
            data.mkdir()
            (data / "topics.json").write_text('{"schema_version": 1, "topics": [{"id": "Bad"}]}')
            code, _, err = self.run_cli("--data", str(data), "validate")
            self.assertEqual(code, 1)
            self.assertIn("error:", err)
