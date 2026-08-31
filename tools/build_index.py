"""Build the deterministic catalog consumed by Luminesk CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from luminesk_cli.domain.catalog import parse_catalog_index
from luminesk_cli.domain.errors import ValidationError
from luminesk_cli.domain.manifest import LocalFileOptions, Manifest, load_manifest
from luminesk_cli.infrastructure.template import read_template_tree

REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
RESERVED_DIRECTORIES = frozenset(
    {
        ".ci",
        ".git",
        ".github",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "dist",
        "schemas",
        "tests",
        "tools",
    }
)


def discover_entries(root: Path) -> tuple[Path, ...]:
    """Return canonical root-level recipe directories in stable order."""

    entries: list[Path] = []

    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if child.name.startswith(".") or child.name in RESERVED_DIRECTORIES:
            continue

        if not child.is_dir():
            continue

        manifest_path = child / "luminesk.toml"

        if not manifest_path.is_file():
            raise ValidationError(
                f"root recipe directory has no luminesk.toml: {child.name}"
            )

        entries.append(child)

    return tuple(entries)


def entry_document(entry_root: Path, manifest: Manifest) -> dict[str, object]:
    """Convert a validated manifest into its public search metadata."""

    package = manifest.package

    if entry_root.name != package.name:
        raise ValidationError(
            "recipe directory must equal package.name",
            path=entry_root.name,
        )

    if not package.summary:
        raise ValidationError("official recipes require package.summary")

    for source in manifest.sources:
        if isinstance(source.options, LocalFileOptions):
            raise ValidationError(
                "official recipes may not use local-file sources",
                path=package.name,
            )

    template = read_template_tree(entry_root, manifest)
    document: dict[str, object] = {
        "name": package.name,
        "displayName": package.display_name or package.name,
        "recipeVersion": package.version,
        "kind": package.kind,
        "game": package.game,
        "edition": package.edition,
        "summary": package.summary,
        "keywords": list(package.keywords),
        "path": package.name,
        "manifestDigest": manifest.digest,
    }

    if template is not None:
        document["templateDigest"] = template.digest

    return document


def build_index(root: Path, revision: str) -> bytes:
    """Build canonical index bytes for an immutable content revision."""

    if REVISION_RE.fullmatch(revision) is None:
        raise ValidationError("revision must be a lowercase 40-character Git SHA")

    entries = [
        entry_document(entry_root, load_manifest(entry_root / "luminesk.toml"))
        for entry_root in discover_entries(root)
    ]
    document = {
        "entries": entries,
        "indexVersion": 1,
        "revision": revision,
    }
    content = (
        json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")
    parse_catalog_index(content)
    return content


def digest_document(content: bytes) -> bytes:
    digest = hashlib.sha256(content).hexdigest()
    return f"{digest}  index-v1.json\n".encode("ascii")


def write_index(output: Path, content: bytes) -> None:
    """Atomically write the index and its checksum file."""

    output.mkdir(parents=True, exist_ok=True)
    _atomic_write(output / "index-v1.json", content)
    _atomic_write(output / "index-v1.json.sha256", digest_document(content))


def check_index(output: Path, content: bytes) -> None:
    expected = {
        output / "index-v1.json": content,
        output / "index-v1.json.sha256": digest_document(content),
    }

    for path, value in expected.items():
        try:
            actual = path.read_bytes()
        except OSError as exc:
            raise ValidationError(f"generated catalog file is missing: {path}") from exc

        if actual != value:
            raise ValidationError(f"generated catalog file is stale: {path}")


def _atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )

    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass

        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    root = arguments.root.resolve()
    output = (arguments.output or root / "dist").resolve()
    content = build_index(root, arguments.revision)

    if arguments.check:
        check_index(output, content)
        print(f"Verified {len(parse_catalog_index(content).entries)} catalog entries.")
    else:
        write_index(output, content)
        print(f"Built {len(parse_catalog_index(content).entries)} catalog entries.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
