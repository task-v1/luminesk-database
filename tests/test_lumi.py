from __future__ import annotations

import gzip
import json
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest
from luminesk_cli.cli.entry import main
from luminesk_cli.domain.catalog import parse_catalog_index
from luminesk_cli.domain.manifest import MavenOptions, load_manifest
from luminesk_cli.infrastructure.catalog import CatalogClient, CatalogStore

from tools.build_index import build_index
from tools.validate import validate_repository

REVISION = "b" * 40


def _gzip_response(content: bytes) -> httpx.Response:
    compressed = gzip.compress(content, mtime=0)
    return httpx.Response(
        200,
        content=compressed,
        headers={
            "Content-Encoding": "gzip",
            "Content-Length": str(len(compressed)),
        },
    )


def test_lumi_recipe_matches_runtime_contract(repository_root: Path) -> None:
    manifest = load_manifest(repository_root / "database" / "lumi" / "luminesk.toml")

    assert manifest.package.name == "lumi"
    assert manifest.package.display_name == "Lumi"
    assert manifest.package.edition == "bedrock"
    assert manifest.package.platforms == ("linux/amd64", "linux/arm64")
    assert len(manifest.sources) == 1
    source = manifest.sources[0]
    assert source.type == "maven"
    assert isinstance(source.options, MavenOptions)
    assert source.options.repository == "https://repo.lumi.su/releases"
    assert source.options.group == "com.koshakmine"
    assert source.options.artifact == "Lumi"
    assert source.options.version == "latest"
    assert manifest.runtime.image.startswith("eclipse-temurin:21-jre@sha256:")
    assert manifest.runtime.run_as == "${input.runtime_uid}:${input.runtime_gid}"
    assert manifest.runtime.ports[0].protocol == "udp"
    assert manifest.runtime.ports[0].container == 19132


def test_repository_and_cli_search_info_work_together(
    repository_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    validate_repository(repository_root)
    content = build_index(repository_root, REVISION)
    snapshot = parse_catalog_index(content)
    store = CatalogStore(tmp_path / "catalog")
    store.commit(snapshot, content)
    monkeypatch.setattr(
        "luminesk_cli.cli.commands.catalog.catalog_store",
        lambda: store,
    )

    assert main(["search", "lumi", "--edition", "bedrock", "--json"]) == 0
    search = json.loads(capsys.readouterr().out)
    assert search["recipes"][0]["name"] == "lumi"

    assert main(["info", "lumi", "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["recipe"]["displayName"] == "Lumi"
    assert info["recipe"]["recipeVersion"] == "1.0.2"
    assert info["recipe"]["license"] == "LGPL-3.0-only"


def test_catalog_client_acquires_exact_lumi_recipe(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    content = build_index(repository_root, REVISION)
    snapshot = parse_catalog_index(content)
    entry = next(entry for entry in snapshot.entries if entry.name == "lumi")
    manifest = (repository_root / "database" / "lumi" / "luminesk.toml").read_bytes()
    template = (
        repository_root / "database" / "lumi" / "template" / "settings.yml.tmpl"
    ).read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        path = unquote(request.url.path)

        if path.endswith(f"/{REVISION}/database/lumi/luminesk.toml"):
            return _gzip_response(manifest)

        if path.endswith("/contents/database/lumi/template"):
            return httpx.Response(
                200,
                json=[
                    {
                        "type": "file",
                        "path": "database/lumi/template/settings.yml.tmpl",
                        "size": len(template),
                        "download_url": "https://download.example/settings.yml.tmpl",
                    }
                ],
            )

        if request.url.host == "download.example":
            return _gzip_response(template)

        raise AssertionError(f"unexpected catalog request: {request.url}")

    store = CatalogStore(tmp_path / "catalog")
    client = CatalogClient(
        store,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        allow_private_network=True,
    )
    acquired = client.acquire_entry(snapshot, entry, tmp_path / "recipe")

    assert acquired.manifest.package.name == "lumi"
    assert acquired.origin.kind == "database"
    assert acquired.origin.revision == REVISION
    assert (acquired.root / "template" / "settings.yml.tmpl").read_bytes() == template
