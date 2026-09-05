from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from luminesk_cli.domain.errors import SecurityError, ValidationError
from luminesk_cli.domain.manifest import SOURCE_TYPES

from tools import validate
from tools.validate import PRIVATE_KEY_MARKERS, _validate_tree


@pytest.mark.parametrize("marker", PRIVATE_KEY_MARKERS)
def test_recipe_tree_rejects_every_private_key_marker(
    tmp_path: Path,
    marker: bytes,
) -> None:
    recipe = tmp_path / "recipe"
    recipe.mkdir()
    (recipe / "notes.txt").write_bytes(b"prefix\n" + marker + b"\nsuffix\n")

    with pytest.raises(SecurityError, match="private key material"):
        _validate_tree(recipe)


@pytest.mark.parametrize("name", [".env", "id_rsa", "server.pem", "server.jar"])
def test_recipe_tree_rejects_secret_names_and_archives(
    tmp_path: Path,
    name: str,
) -> None:
    recipe = tmp_path / "recipe"
    recipe.mkdir()
    (recipe / name).write_bytes(b"content")

    with pytest.raises(SecurityError):
        _validate_tree(recipe)


def test_recipe_tree_rejects_links_and_size_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe = tmp_path / "recipe"
    recipe.mkdir()
    source = recipe / "source.txt"
    source.write_bytes(b"12")
    (recipe / "link.txt").symlink_to(source)

    with pytest.raises(SecurityError, match="symlinks"):
        _validate_tree(recipe)

    (recipe / "link.txt").unlink()
    os.link(source, recipe / "hardlink.txt")
    with pytest.raises(SecurityError, match="special file"):
        _validate_tree(recipe)

    (recipe / "hardlink.txt").unlink()
    monkeypatch.setattr(validate, "MAX_RECIPE_FILE_SIZE", 1)
    with pytest.raises(SecurityError, match="file exceeds"):
        _validate_tree(recipe)

    monkeypatch.setattr(validate, "MAX_RECIPE_FILE_SIZE", 10)
    monkeypatch.setattr(validate, "MAX_RECIPE_SIZE", 1)
    with pytest.raises(SecurityError, match="total size"):
        _validate_tree(recipe)


def test_supported_source_contract_rejects_invalid_documents(tmp_path: Path) -> None:
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    path = schemas / "supported-source-types-v1.json"

    for document, message in (
        ([], "must be an object"),
        ({"production": [], "development": "local-file"}, "lists are invalid"),
        (
            {"production": [], "development": ["local-file"]},
            "production source type",
        ),
        (
            {
                "production": sorted(set(SOURCE_TYPES) - {"local-file"}),
                "development": [],
            },
            "development source type",
        ),
    ):
        path.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(ValidationError, match=message):
            validate._validate_supported_sources(tmp_path)

    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValidationError, match="contract is invalid"):
        validate._validate_supported_sources(tmp_path)


def test_dist_validation_rejects_missing_and_bad_checksum(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="artifacts are missing"):
        validate._validate_dist(tmp_path)

    shutil.copytree(repository_root / "dist", tmp_path / "dist")
    (tmp_path / "dist" / "index-v1.json.sha256").write_text(
        "0" * 64 + "  index-v1.json\n", encoding="ascii"
    )
    with pytest.raises(ValidationError, match="checksum"):
        validate._validate_dist(tmp_path)


def test_version_bump_validation_uses_semver_ordering(
    repository_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shutil.copytree(repository_root / "database", tmp_path / "database")
    current = (tmp_path / "database" / "lumi" / "luminesk.toml").read_text(
        encoding="utf-8"
    )

    monkeypatch.setattr(
        validate,
        "_git",
        lambda root, *arguments: (
            "database/lumi/template/settings.yml.tmpl\n"
            if arguments[0] == "diff"
            else current
        ),
    )
    monkeypatch.setattr(validate, "_git_optional", lambda root, *arguments: current)

    with pytest.raises(ValidationError, match="without a recipe version bump"):
        validate.validate_version_bumps(tmp_path, "base")

    manifest_path = tmp_path / "database" / "lumi" / "luminesk.toml"
    manifest_path.write_text(
        current.replace('version = "1.0.1"', 'version = "1.0.2"', 1),
        encoding="utf-8",
    )
    validate.validate_version_bumps(tmp_path, "base")

    assert validate._semver_key("1.0.0-rc.2") < validate._semver_key("1.0.0")
    assert validate._semver_key("1.0.0-alpha") < validate._semver_key("1.0.0-beta")


def test_git_helpers_report_failures(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="not a git repository"):
        validate._git(tmp_path, "status")
    assert validate._git_optional(tmp_path, "status") is None
