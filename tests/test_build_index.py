from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from luminesk_cli.domain.catalog import parse_catalog_index
from luminesk_cli.domain.errors import ValidationError

from tools.build_index import build_index, check_index, write_index

REVISION = "a" * 40


def test_index_is_deterministic_and_describes_lumi(repository_root: Path) -> None:
    first = build_index(repository_root, REVISION)
    second = build_index(repository_root, REVISION)

    assert first == second
    snapshot = parse_catalog_index(first)
    assert snapshot.revision == REVISION
    assert len(snapshot.entries) == 1
    entry = snapshot.entries[0]
    assert entry.name == "lumi"
    assert entry.display_name == "Lumi"
    assert entry.edition == "bedrock"
    assert entry.template_digest is not None


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
    recipe = tmp_path / "fixture"
    recipe.mkdir()
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
