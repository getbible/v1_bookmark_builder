from __future__ import annotations

import hashlib
import json
import re
import unittest
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from catalog import Catalog
from render import RESOURCES, PublishedState, render_api
from sources import load_catalog
from tests.helpers import sample_catalog

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - dev requirement
    jsonschema = None

try:
    import openapi_spec_validator
except ImportError:  # pragma: no cover - dev requirement
    OPENAPI_VALIDATOR_AVAILABLE = False
else:
    OPENAPI_VALIDATOR_AVAILABLE = True

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
RESPONSE_COMPONENTS = {
    "/index.json": "Index",
    "/all.json": "All",
    "/catalog.json": "Catalog",
    "/topics.json": "Topics",
    "/topics/{id}.json": "Topic",
    "/verses/{book}.json": "Book",
    "/verses/{book}/{chapter}.json": "Chapter",
    "/locales.json": "Locales",
    "/locales/{locale}.json": "Locale",
    "/checksums.json": "Checksums",
}


def _objects(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def _media(spec: dict[str, Any], path: str) -> dict[str, Any]:
    media = spec["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]
    assert isinstance(media, dict)
    return media


def _parameters(spec: dict[str, Any], path: str) -> dict[str, dict[str, Any]]:
    item = spec["paths"][path]
    parameters = {}
    for parameter in (*item.get("parameters", []), *item["get"].get("parameters", [])):
        if "$ref" in parameter:
            reference = parameter["$ref"]
            assert reference.startswith("#/components/parameters/")
            parameter = spec["components"]["parameters"][reference.rsplit("/", 1)[1]]
        parameters[parameter["name"]] = parameter
    return parameters


def _parameter_example(parameter: dict[str, Any]) -> Any:
    return parameter.get("example", parameter["schema"].get("example"))


def _examples(media: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if "example" in media:
        yield {"value": media["example"]}
    yield from media.get("examples", {}).values()


def _matching_path(spec: dict[str, Any], relative: str) -> str:
    for path in spec["paths"]:
        pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path))
        if re.fullmatch(pattern, "/" + relative):
            assert isinstance(path, str)
            return path
    raise AssertionError(f"No OpenAPI operation describes {relative}")


class OpenApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.files = render_api(sample_catalog())
        self.spec = json.loads(self.files["openapi.json"])

    def test_discovery_and_operations_cover_every_resource(self) -> None:
        self.assertEqual(RESOURCES["openapi"], "openapi.json")
        self.assertEqual(
            json.loads(self.files["index.json"])["resources"]["openapi"], "openapi.json"
        )
        self.assertEqual(self.spec["openapi"], "3.1.1")
        self.assertEqual([server["url"] for server in self.spec["servers"]], ["./"])
        self.assertEqual(set(self.spec["paths"]), {*RESPONSE_COMPONENTS, "/openapi.json"})
        self.assertEqual(set(self.spec["paths"]), {"/" + path for path in RESOURCES.values()})
        operation_ids = []
        for path, item in self.spec["paths"].items():
            with self.subTest(path=path):
                self.assertEqual(
                    set(item)
                    & {"get", "post", "put", "patch", "delete", "head", "options", "trace"},
                    {"get"},
                )
                operation = item["get"]
                operation_ids.append(operation["operationId"])
                self.assertTrue(operation["summary"])
                self.assertTrue(operation["responses"]["200"]["description"])
                media = _media(self.spec, path)
                if path in RESPONSE_COMPONENTS:
                    self.assertEqual(
                        media["schema"]["$ref"],
                        "#/components/schemas/" + RESPONSE_COMPONENTS[path],
                    )
                else:
                    self.assertEqual(media["schema"]["type"], "object")
                    self.assertEqual(list(_examples(media)), [])
                self.assertEqual(
                    set(_parameters(self.spec, path)), set(re.findall(r"\{([^}]+)\}", path))
                )
                for parameter in _parameters(self.spec, path).values():
                    self.assertEqual(parameter["in"], "path")
                    self.assertIs(parameter["required"], True)
        self.assertEqual(len(operation_ids), len(set(operation_ids)))

    def test_schema_references_are_self_contained_and_resolve(self) -> None:
        self.assertEqual(set(self.spec["components"]["schemas"]), set(RESPONSE_COMPONENTS.values()))
        for node in _objects(self.spec["components"]["schemas"]):
            self.assertNotIn("$id", node)
        references = [node["$ref"] for node in _objects(self.spec) if "$ref" in node]
        self.assertTrue(references)
        for reference in references:
            with self.subTest(reference=reference):
                self.assertTrue(
                    reference.startswith("#/"), "Schema resolution must not need a network"
                )
                target = self.spec
                for token in reference[2:].split("/"):
                    target = target[token.replace("~1", "/").replace("~0", "~")]
                self.assertIsInstance(target, dict)

    def test_examples_resolve_to_the_actual_rendered_payloads(self) -> None:
        for path in RESPONSE_COMPONENTS:
            with self.subTest(path=path):
                media = _media(self.spec, path)
                examples = list(_examples(media))
                self.assertTrue(examples)
                parameters = _parameters(self.spec, path)
                values = {
                    name: _parameter_example(parameter) for name, parameter in parameters.items()
                }
                self.assertTrue(all(value is not None for value in values.values()))
                relative = path.lstrip("/").format(**values)
                expected = json.loads(self.files[relative])
                for example in examples:
                    self.assertNotEqual("value" in example, "externalValue" in example)
                    if "externalValue" in example:
                        self.assertEqual(example["externalValue"], "./" + relative)
                    else:
                        self.assertEqual(example["value"], expected)
                if not parameters:
                    self.assertTrue(all("externalValue" in example for example in examples))
        self.assertEqual(
            _parameter_example(_parameters(self.spec, "/locales/{locale}.json")["locale"]), "en"
        )

    def test_deleted_topic_does_not_survive_in_examples(self) -> None:
        catalog = sample_catalog()
        catalog.delete_topic("gods-judgment")
        files = render_api(catalog)
        self.assertNotIn(b"gods-judgment", files["openapi.json"])
        spec = json.loads(files["openapi.json"])
        identifier = _parameter_example(_parameters(spec, "/topics/{id}.json")["id"])
        self.assertEqual(identifier, "grace")
        topic_examples = list(_examples(_media(spec, "/topics/{id}.json")))
        self.assertTrue(topic_examples)
        self.assertEqual(topic_examples[0]["value"], json.loads(files["topics/grace.json"]))

    def test_empty_catalog_has_no_fabricated_topic_example(self) -> None:
        files = render_api(Catalog())
        spec = json.loads(files["openapi.json"])
        parameter = _parameters(spec, "/topics/{id}.json")["id"]
        self.assertIsNone(_parameter_example(parameter))
        self.assertEqual(list(_examples(_media(spec, "/topics/{id}.json"))), [])
        for path in ("/verses/{book}.json", "/verses/{book}/{chapter}.json"):
            values = {
                name: _parameter_example(parameter)
                for name, parameter in _parameters(spec, path).items()
            }
            self.assertTrue(all(value == 1 for value in values.values()))
            examples = list(_examples(_media(spec, path)))
            self.assertTrue(examples)
            self.assertEqual(examples[0]["value"], json.loads(files[path[1:].format(**values)]))

    def test_topic_without_verses_still_has_valid_examples(self) -> None:
        catalog = Catalog()
        catalog.create_topic(name="No Verses Yet", color_value="#ffffff")
        files = render_api(catalog)
        spec = json.loads(files["openapi.json"])
        self.assertEqual(
            list(_examples(_media(spec, "/topics/{id}.json")))[0]["value"]["verses"], []
        )
        for path in ("/verses/{book}.json", "/verses/{book}/{chapter}.json"):
            values = {
                name: _parameter_example(parameter)
                for name, parameter in _parameters(spec, path).items()
            }
            self.assertEqual(
                list(_examples(_media(spec, path)))[0]["value"],
                json.loads(files[path[1:].format(**values)]),
            )

    def test_spec_is_deterministic_and_checksum_covers_its_bytes(self) -> None:
        catalog = sample_catalog()
        checksum = json.loads(self.files["index.json"])["checksum"]
        for previous in (
            None,
            PublishedState(catalog_version=9, checksum=checksum),
            PublishedState(catalog_version=9, checksum="0" * 64),
        ):
            files = render_api(catalog, previous=previous)
            self.assertEqual(files["openapi.json"], self.files["openapi.json"])
            self.assertEqual(
                json.loads(files["checksums.json"])["files"]["openapi.json"],
                hashlib.sha256(files["openapi.json"]).hexdigest(),
            )

    def test_large_topic_examples_reference_the_complete_published_payload(self) -> None:
        catalog = Catalog()
        catalog.create_topic(
            name="Many Verses",
            color_value="#ffffff",
            verses=[[1, chapter, verse] for chapter in range(1, 51) for verse in range(1, 26)],
        )
        files = render_api(catalog)
        spec = json.loads(files["openapi.json"])
        self.assertGreater(len(files["topics/many-verses.json"]), 16384)
        examples = list(_examples(_media(spec, "/topics/{id}.json")))
        self.assertTrue(examples)
        self.assertEqual(examples[0]["externalValue"], "./topics/many-verses.json")
        self.assertNotIn("value", examples[0])

    @unittest.skipUnless(OPENAPI_VALIDATOR_AVAILABLE, "openapi-spec-validator is not installed")
    def test_generated_description_is_a_valid_openapi_document(self) -> None:
        partial = sample_catalog()
        partial.set_locale_names("es", {"grace": "Gracia"})
        for catalog in (partial, Catalog()):
            with self.subTest(topics=len(catalog.topics)):
                openapi_spec_validator.validate(json.loads(render_api(catalog)["openapi.json"]))


@unittest.skipIf(jsonschema is None, "jsonschema is not installed")
class OpenApiSchemaTests(unittest.TestCase):
    def test_every_rendered_document_validates_against_its_openapi_response(self) -> None:
        partial = sample_catalog()
        partial.set_locale_names("es", {"grace": "Gracia"})
        files = render_api(partial)
        self.assertNotIn("name", json.loads(files["locales/es.json"]))
        self.assertEqual(json.loads(files["locales/es.json"])["topics"], {"grace": "Gracia"})
        for catalog in (partial, Catalog(), load_catalog(REPOSITORY_ROOT / "data")):
            files = render_api(catalog)
            spec = json.loads(files["openapi.json"])
            validators = {}
            for path in spec["paths"]:
                schema = {**_media(spec, path)["schema"], "components": spec["components"]}
                Draft202012Validator.check_schema(schema)
                validators[path] = Draft202012Validator(schema)
            for relative, content in files.items():
                with self.subTest(topics=len(catalog.topics), relative=relative):
                    path = _matching_path(spec, relative)
                    errors = list(validators[path].iter_errors(json.loads(content)))
                    self.assertEqual(errors, [], [error.message for error in errors[:3]])
            for path in RESPONSE_COMPONENTS:
                for example in _examples(_media(spec, path)):
                    if "value" in example:
                        validators[path].validate(example["value"])

    def test_parameters_accept_examples_and_enforce_api_bounds(self) -> None:
        cases: dict[str, tuple[list[object], list[object]]] = {
            "id": (["grace", "gods-judgment"], ["Grace", "-grace", "a" * 81, ""]),
            "book": ([1, 66], [0, 67, True]),
            "chapter": ([1, 150], [0, 151, True]),
            "locale": (["en", "zh-hant"], ["EN", "zh_hant", "a", "a" * 17]),
        }
        for catalog in (sample_catalog(), Catalog()):
            spec = json.loads(render_api(catalog)["openapi.json"])
            for path in spec["paths"]:
                for name, parameter in _parameters(spec, path).items():
                    with self.subTest(topics=len(catalog.topics), path=path, name=name):
                        validator = Draft202012Validator(parameter["schema"])
                        example = _parameter_example(parameter)
                        if example is not None:
                            validator.validate(example)
                        valid, invalid = cases[name]
                        for value in valid:
                            self.assertTrue(validator.is_valid(value), repr(value))
                        for value in invalid:
                            self.assertFalse(validator.is_valid(value), repr(value))

    def test_components_preserve_strict_payload_constraints(self) -> None:
        spec = json.loads(render_api(sample_catalog())["openapi.json"])
        components = spec["components"]
        locale_validator = Draft202012Validator(
            {"$ref": "#/components/schemas/Locale", "components": components}
        )
        locale_validator.validate({"schema_version": 1, "locale": "es", "topics": {}})
        self.assertFalse(locale_validator.is_valid({"schema_version": 1, "locale": "es"}))
        self.assertFalse(
            locale_validator.is_valid(
                {"schema_version": 1, "locale": "es", "topics": {}, "name": None}
            )
        )
        topic = json.loads(render_api(sample_catalog())["topics/grace.json"])
        topic["verses"] = [[49, 2, 8, 9]]
        topic_validator = Draft202012Validator(
            {"$ref": "#/components/schemas/Topic", "components": components}
        )
        self.assertFalse(topic_validator.is_valid(topic))
