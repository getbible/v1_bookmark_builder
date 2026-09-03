"""Command line interface: validate, normalize and build the sources, import robot bundles."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .build import (
    RESOURCES,
    catalog_checksum,
    catalog_version,
    read_published_state,
    render_api,
    stale_paths,
    write_tree,
)
from .bundle import apply_bundle
from .model import CatalogError
from .sources import load_catalog, save_catalog


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    options = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if options.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        handler = options.handler
        result: int = handler(options)
        return result
    except CatalogError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bookmark-builder",
        description="Validate the getBible bookmark sources and render the static v1 JSON API.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data"),
        help="directory holding topics.json, links/ and locales/ (default: ./data)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate the canonical sources")
    validate.set_defaults(handler=_validate)

    build = commands.add_parser("build", help="render the static API tree from the sources")
    build.add_argument(
        "--output",
        type=Path,
        default=Path("v1"),
        help="directory to (re)create; its existing index.json supplies the previous version",
    )
    build.add_argument(
        "--check",
        action="store_true",
        help="report whether --output already matches a fresh build instead of writing",
    )
    build.set_defaults(handler=_build)

    normalize = commands.add_parser(
        "normalize", help="rewrite the sources in the builder's canonical formatting"
    )
    normalize.set_defaults(handler=_normalize)

    bundle = commands.add_parser(
        "import-bundle", help="apply a robot contribution bundle to the sources"
    )
    bundle.add_argument("bundle", type=Path, help="path to the schema-version-1 bundle JSON")
    bundle.add_argument("--check", action="store_true", help="validate without writing")
    bundle.set_defaults(handler=_import_bundle)
    return parser


def _validate(options: argparse.Namespace) -> int:
    catalog = load_catalog(options.data)
    print(
        f"OK: {len(catalog.topics)} topics, {catalog.link_count()} verse links, "
        f"{len(catalog.locales)} locales."
    )
    return 0


def _normalize(options: argparse.Namespace) -> int:
    catalog = load_catalog(options.data)
    changed = save_catalog(options.data, catalog)
    if changed:
        shown = ", ".join(changed[:8]) + (" ..." if len(changed) > 8 else "")
        print(f"Normalized {len(changed)} source file(s): {shown}")
    else:
        print("The sources are already in canonical form.")
    return 0


def _build(options: argparse.Namespace) -> int:
    catalog = load_catalog(options.data)
    previous = read_published_state(options.output / RESOURCES["index"])
    files = render_api(catalog, previous=previous)
    version = catalog_version(files)
    checksum = catalog_checksum(files)
    if options.check:
        stale = stale_paths(options.output, files)
        if stale:
            shown = ", ".join(stale[:8]) + (" ..." if len(stale) > 8 else "")
            print(f"STALE: {len(stale)} file(s) differ from a fresh build: {shown}")
            return 1
        print(f"Up to date: {len(files)} files (catalogue version {version}, checksum {checksum}).")
        return 0
    write_tree(options.output, files)
    state = "unchanged" if previous and previous.checksum == checksum else "changed"
    print(
        f"Generated {len(files)} files into {options.output} "
        f"(catalogue version {version}, checksum {checksum}, content {state})."
    )
    return 0


def _import_bundle(options: argparse.Namespace) -> int:
    catalog = load_catalog(options.data)
    try:
        document = json.loads(options.bundle.read_text("utf-8"))
    except (OSError, ValueError) as error:
        raise CatalogError(f"{options.bundle} is not readable JSON: {error}") from error
    result = apply_bundle(catalog, document)
    if not result.changed():
        print("The bundle is already fully applied; nothing to do.")
        return 0
    catalog.validate()
    summary = (
        f"created {len(result.topics_created)} topic(s), extended "
        f"{len(result.topics_extended)}, added {result.verses_added} and removed "
        f"{result.verses_removed} verse link(s)"
    )
    if options.check:
        print(f"Valid: would have {summary}.")
        return 0
    changed = save_catalog(options.data, catalog)
    print(f"Applied: {summary}; {len(changed)} source file(s) written.")
    return 0


__all__ = ["build_parser", "main"]
