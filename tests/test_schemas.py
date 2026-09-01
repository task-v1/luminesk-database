from __future__ import annotations

import json
import re
from pathlib import Path

from luminesk_cli.domain.manifest import SOURCE_TYPES

WORKFLOW_USE_RE = re.compile(r"^\s*uses:\s*(?P<action>[^\s#]+)", re.MULTILINE)
COMMIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
CLI_REVISION_RE = re.compile(r'^\s*CLI_REVISION: "([0-9a-f]{40})"$', re.MULTILINE)


def _schema(repository_root: Path, name: str) -> dict[str, object]:
    value = json.loads((repository_root / "schemas" / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_source_type_contract_matches_cli(repository_root: Path) -> None:
    metadata = _schema(repository_root, "supported-source-types-v1.json")
    production = metadata["production"]
    development = metadata["development"]

    assert isinstance(production, list)
    assert isinstance(development, list)
    assert production == sorted(production)
    assert development == ["local-file"]
    assert set(production) | set(development) == SOURCE_TYPES
    assert set(production).isdisjoint(development)


def test_manifest_schema_exposes_only_production_sources(
    repository_root: Path,
) -> None:
    schema = _schema(repository_root, "luminesk-v1.schema.json")
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    source = definitions["source"]
    assert isinstance(source, dict)
    properties = source["properties"]
    assert isinstance(properties, dict)
    source_type = properties["type"]
    assert isinstance(source_type, dict)
    declared = source_type["enum"]
    assert isinstance(declared, list)

    metadata = _schema(repository_root, "supported-source-types-v1.json")
    production = metadata["production"]
    assert isinstance(production, list)
    assert set(declared) == set(production)
    assert "local-file" not in declared


def test_index_schema_requires_database_recipe_paths(
    repository_root: Path,
) -> None:
    schema = _schema(repository_root, "index-v1.schema.json")
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    recipe_path = definitions["recipePath"]
    assert isinstance(recipe_path, dict)
    assert recipe_path["pattern"] == (
        "^database/[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$"
    )

    entry = definitions["entry"]
    assert isinstance(entry, dict)
    properties = entry["properties"]
    assert isinstance(properties, dict)
    assert properties["path"] == {"$ref": "#/$defs/recipePath"}


def test_workflows_pin_external_actions_and_the_same_cli_revision(
    repository_root: Path,
) -> None:
    revisions = set()

    for path in (repository_root / ".github" / "workflows").glob("*.yml"):
        content = path.read_text(encoding="utf-8")
        revisions.update(CLI_REVISION_RE.findall(content))

        for match in WORKFLOW_USE_RE.finditer(content):
            action = match.group("action")
            if action.startswith("./"):
                continue
            _, separator, revision = action.rpartition("@")
            assert separator and COMMIT_SHA_RE.fullmatch(revision), (
                f"{path.name} has a mutable action: {action}"
            )

    assert revisions == {"a6fe549e8d63cecfb1877e37e9a73ab3e8ce883f"}
