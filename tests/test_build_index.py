from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from luminesk_cli.domain.catalog import parse_catalog_index
from luminesk_cli.domain.errors import ValidationError
from luminesk_cli.domain.manifest import load_manifest, parse_manifest

from tools import build_index as build_index_module
from tools.build_index import (
    build_index,
    check_index,
    discover_entries,
    entry_document,
    write_index,
)
from tools.validate import validate_repository

REVISION = "a" * 40


def test_index_is_deterministic_and_describes_lumi_by_name(
    repository_root: Path,
) -> None:
    first = build_index(repository_root, REVISION)
    second = build_index(repository_root, REVISION)

    assert first == second
    snapshot = parse_catalog_index(first)
    assert snapshot.revision == REVISION
    entries = {entry.name: entry for entry in snapshot.entries}
    assert tuple(entries) == tuple(sorted(entries))
    entry = entries["lumi"]
    assert entry.name == "lumi"
    assert entry.path == "database/lumi"
    assert entry.display_name == "Lumi"
    assert entry.edition == "bedrock"
    assert entry.template_digest is not None


def test_index_supports_multiple_cores_with_optional_templates(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    database = root / "database"
    database.mkdir(parents=True)
    shutil.copytree(repository_root / "database" / "lumi", database / "lumi")
    shutil.copytree(repository_root / "schemas", root / "schemas")

    alpha = database / "alpha"
    alpha.mkdir()
    manifest = (repository_root / "database" / "lumi" / "luminesk.toml").read_text(
        encoding="utf-8"
    )
    manifest = manifest.replace('template = "template"\n', "", 1)
    manifest = manifest.replace('name = "lumi"', 'name = "alpha"', 1)
    manifest = manifest.replace('display_name = "Lumi"', 'display_name = "Alpha"', 1)
    (alpha / "luminesk.toml").write_text(manifest, encoding="utf-8")

    assert validate_repository(root) == 2
    snapshot = parse_catalog_index(build_index(root, REVISION))
    entries = {entry.name: entry for entry in snapshot.entries}

    assert tuple(entries) == ("alpha", "lumi")
    assert entries["alpha"].path == "database/alpha"
    assert entries["alpha"].template_digest is None
    assert entries["lumi"].template_digest is not None


def test_index_writer_emits_matching_checksum(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    content = build_index(repository_root, REVISION)

    write_index(tmp_path, content)
    check_index(tmp_path, content)

    digest = hashlib.sha256(content).hexdigest()
    assert (tmp_path / "index-v1.json.sha256").read_text() == (
        f"{digest}  index-v1.json\n"
    )


def test_official_index_rejects_local_file_sources(tmp_path: Path) -> None:
    recipe = tmp_path / "database" / "fixture"
    recipe.mkdir(parents=True)
    (recipe / "server.bin").write_bytes(b"fixture")
    (recipe / "luminesk.toml").write_text(
        """\
manifest_version = 1
[package]
name = "fixture"
version = "1.0.0"
kind = "core"
game = "minecraft"
edition = "bedrock"
summary = "Fixture"
[[sources]]
id = "core"
type = "local-file"
target = "server.bin"
[sources.options]
path = "server.bin"
[runtime]
image = "example.invalid/server@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
command = ["./server.bin"]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="local-file"):
        build_index(tmp_path, REVISION)


def test_index_bytes_are_canonical_json(repository_root: Path) -> None:
    content = build_index(repository_root, REVISION)
    document = json.loads(content)

    assert (
        content
        == (
            json.dumps(
                document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            )
            + "\n"
        ).encode()
    )


def test_discovery_rejects_unsafe_database_layout(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="safe database"):
        discover_entries(tmp_path)

    database = tmp_path / "database"
    database.mkdir()
    (database / "file").write_text("not a recipe", encoding="utf-8")
    with pytest.raises(ValidationError, match="must be directories"):
        discover_entries(tmp_path)

    (database / "file").unlink()
    (database / "fixture").mkdir()
    with pytest.raises(ValidationError, match="no luminesk.toml"):
        discover_entries(tmp_path)


def test_entry_metadata_requires_matching_name_and_summary(
    repository_root: Path,
) -> None:
    root = repository_root / "database" / "lumi"
    manifest = load_manifest(root / "luminesk.toml")

    with pytest.raises(ValidationError, match="directory must equal"):
        entry_document(root.with_name("other"), manifest)

    empty_summary = (
        (root / "luminesk.toml")
        .read_bytes()
        .replace(b'summary = "Lumi Minecraft Bedrock server"', b'summary = ""')
    )
    with pytest.raises(ValidationError, match="require package.summary"):
        entry_document(root, parse_manifest(empty_summary))


def test_index_rejects_invalid_revision_and_stale_outputs(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="40-character Git SHA"):
        build_index(repository_root, "main")

    content = build_index(repository_root, REVISION)
    with pytest.raises(ValidationError, match="missing"):
        check_index(tmp_path, content)

    write_index(tmp_path, content)
    (tmp_path / "index-v1.json").write_bytes(b"stale")
    with pytest.raises(ValidationError, match="stale"):
        check_index(tmp_path, content)


def test_build_index_main_writes_and_checks_output(
    repository_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        build_index_module.main(
            [
                "--root",
                str(repository_root),
                "--revision",
                REVISION,
                "--output",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert "Built 1 catalog entries" in capsys.readouterr().out

    assert (
        build_index_module.main(
            [
                "--root",
                str(repository_root),
                "--revision",
                REVISION,
                "--output",
                str(tmp_path),
                "--check",
            ]
        )
        == 0
    )
    assert "Verified 1 catalog entries" in capsys.readouterr().out
