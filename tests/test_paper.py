from __future__ import annotations

from pathlib import Path

from luminesk_cli.domain.manifest import PaperOptions, load_manifest


def test_paper_recipe_matches_runtime_contract(repository_root: Path) -> None:
    manifest = load_manifest(repository_root / "database" / "paper" / "luminesk.toml")

    assert manifest.package.name == "paper"
    assert manifest.package.display_name == "PaperMC"
    assert manifest.package.edition == "java"
    assert manifest.package.license == "GPL-3.0-only"
    assert manifest.package.platforms == ("linux/amd64", "linux/arm64")
    assert len(manifest.sources) == 1
    source = manifest.sources[0]
    assert source.type == "paper"
    assert isinstance(source.options, PaperOptions)
    assert source.options.minecraft == "1.21.11"
    assert source.options.build == "latest"
    assert manifest.runtime.image.startswith("eclipse-temurin:21-jre@sha256:")
    assert manifest.runtime.run_as == "1000:1000"
    assert manifest.runtime.ports[0].protocol == "tcp"
    assert manifest.runtime.ports[0].container == 25565
    assert manifest.ownership.preserve == ("eula.txt", "server.properties")
