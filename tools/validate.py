"""Validate official database recipes and generated catalog artifacts."""

from __future__ import annotations

import argparse
import json
import stat
import subprocess
from pathlib import Path

from luminesk_cli.domain.catalog import parse_catalog_index
from luminesk_cli.domain.errors import SecurityError, ValidationError
from luminesk_cli.domain.manifest import SOURCE_TYPES, load_manifest
from luminesk_cli.domain.primitives import SEMVER_RE
from luminesk_cli.infrastructure.recipe_snapshot import create_recipe_snapshot

from tools.build_index import digest_document, discover_entries, entry_document

MAX_RECIPE_FILE_SIZE = 16 * 1024 * 1024
MAX_RECIPE_SIZE = 64 * 1024 * 1024
BINARY_SUFFIXES = frozenset(
    {".7z", ".dll", ".dylib", ".exe", ".gz", ".jar", ".phar", ".so", ".tar", ".zip"}
)
SECRET_NAMES = frozenset({".env", "id_dsa", "id_ecdsa", "id_ed25519", "id_rsa"})
SECRET_SUFFIXES = frozenset({".key", ".p12", ".pem", ".pfx"})
PRIVATE_KEY_MARKER = b"-----BEGIN PRIVATE KEY-----"


def validate_repository(root: Path, *, check_dist: bool = False) -> int:
    entries = discover_entries(root)

    for entry_root in entries:
        _validate_tree(entry_root)
        manifest = load_manifest(entry_root / "luminesk.toml")
        entry_document(entry_root, manifest)
        create_recipe_snapshot(entry_root, manifest)

    _validate_supported_sources(root)

    if check_dist:
        _validate_dist(root)

    return len(entries)


def _validate_tree(root: Path) -> None:
    total_size = 0

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        status = path.lstat()

        if stat.S_ISLNK(status.st_mode):
            raise SecurityError("recipe symlinks are forbidden", path=relative)

        if stat.S_ISDIR(status.st_mode):
            continue

        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            raise SecurityError("recipe contains a special file", path=relative)

        if path.suffix.casefold() in BINARY_SUFFIXES:
            raise SecurityError(
                "binary archives are forbidden in recipes", path=relative
            )

        if (
            path.name.casefold() in SECRET_NAMES
            or path.suffix.casefold() in SECRET_SUFFIXES
        ):
            raise SecurityError("secret-bearing files are forbidden", path=relative)

        if status.st_size > MAX_RECIPE_FILE_SIZE:
            raise SecurityError("recipe file exceeds size limit", path=relative)

        total_size += status.st_size

        if total_size > MAX_RECIPE_SIZE:
            raise SecurityError("recipe exceeds total size limit", path=root.name)

        if PRIVATE_KEY_MARKER in path.read_bytes():
            raise SecurityError("private key material is forbidden", path=relative)


def _validate_supported_sources(root: Path) -> None:
    path = root / "schemas" / "supported-source-types-v1.json"

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError("supported source type contract is invalid") from exc

    if not isinstance(document, dict):
        raise ValidationError("supported source type contract must be an object")

    production = document.get("production")
    development = document.get("development")

    if not isinstance(production, list) or not isinstance(development, list):
        raise ValidationError("supported source type lists are invalid")

    if set(production) != set(SOURCE_TYPES) - {"local-file"}:
        raise ValidationError("production source type contract differs from CLI")

    if development != ["local-file"]:
        raise ValidationError("development source type contract differs from CLI")


def _validate_dist(root: Path) -> None:
    index_path = root / "dist" / "index-v1.json"
    digest_path = root / "dist" / "index-v1.json.sha256"

    try:
        content = index_path.read_bytes()
        digest = digest_path.read_bytes()
    except OSError as exc:
        raise ValidationError("published catalog artifacts are missing") from exc

    parse_catalog_index(content)

    if digest != digest_document(content):
        raise ValidationError("published catalog checksum is invalid")


def validate_version_bumps(root: Path, base_ref: str) -> None:
    """Require recipe SemVer bumps for entry changes relative to a Git ref."""

    changed = _git(root, "diff", "--name-only", f"{base_ref}...HEAD").splitlines()
    entries = {entry.name: entry for entry in discover_entries(root)}

    for name, entry_root in entries.items():
        relevant = [
            path
            for path in changed
            if path.startswith(f"database/{name}/")
            and not path.casefold().endswith("readme.md")
        ]

        if not relevant:
            continue

        previous = _git_optional(
            root,
            "show",
            f"{base_ref}:database/{name}/luminesk.toml",
        )

        if previous is None:
            continue

        old_version = _manifest_version(previous)
        new_version = load_manifest(entry_root / "luminesk.toml").package.version

        if _semver_key(new_version) <= _semver_key(old_version):
            raise ValidationError(
                f"{name} changed without a recipe version bump "
                f"({old_version} -> {new_version})"
            )


def _manifest_version(content: str) -> str:
    import tomllib

    try:
        value = tomllib.loads(content)["package"]["version"]
    except (KeyError, tomllib.TOMLDecodeError, TypeError) as exc:
        raise ValidationError("base recipe has no valid package.version") from exc

    if not isinstance(value, str) or SEMVER_RE.fullmatch(value) is None:
        raise ValidationError("base recipe has no valid package.version")

    return value


def _semver_key(
    version: str,
) -> tuple[int, int, int, int, tuple[tuple[int, object], ...]]:
    core, _, _build = version.partition("+")
    release, separator, prerelease = core.partition("-")
    major, minor, patch = (int(part) for part in release.split("."))
    pre_key: list[tuple[int, object]] = []

    if separator:
        for part in prerelease.split("."):
            pre_key.append((0, int(part)) if part.isdigit() else (1, part))

        stable = 0
    else:
        stable = 1

    return major, minor, patch, stable, tuple(pre_key)


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise ValidationError(result.stderr.strip() or "Git command failed")

    return result.stdout


def _git_optional(root: Path, *arguments: str) -> str | None:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base-ref")
    parser.add_argument("--check-dist", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    root = arguments.root.resolve()
    count = validate_repository(root, check_dist=arguments.check_dist)

    if arguments.base_ref:
        validate_version_bumps(root, arguments.base_ref)

    print(f"Validated {count} official Luminesk recipe(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
