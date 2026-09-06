from __future__ import annotations

from pathlib import Path

import pytest
from luminesk_cli.domain.manifest import (
    GitHubReleaseOptions,
    HttpOptions,
    JenkinsOptions,
    Manifest,
    MavenOptions,
    load_manifest,
)


@pytest.fixture
def manifests(repository_root: Path) -> dict[str, Manifest]:
    names = ("allay", "nukkit", "nukkit-mot", "powernukkitx", "purpur")
    return {
        name: load_manifest(repository_root / "database" / name / "luminesk.toml")
        for name in names
    }


@pytest.mark.parametrize(
    ("name", "display_name", "license_name", "java_version"),
    [
        ("allay", "Allay", "LGPL-3.0-only", "21"),
        ("nukkit", "Cloudburst Nukkit", "GPL-3.0-only", "8"),
        ("nukkit-mot", "Nukkit-MOT", "LGPL-3.0-only", "17"),
        ("powernukkitx", "PowerNukkitX", "LGPL-3.0-only", "25"),
        ("purpur", "Purpur", "MIT", "25"),
    ],
)
def test_jvm_recipe_runtime_contracts(
    manifests: dict[str, Manifest],
    name: str,
    display_name: str,
    license_name: str,
    java_version: str,
) -> None:
    manifest = manifests[name]

    assert manifest.package.name == name
    assert manifest.package.display_name == display_name
    assert manifest.package.license == license_name
    assert manifest.package.platforms == ("linux/amd64", "linux/arm64")
    assert manifest.runtime.image.startswith(f"eclipse-temurin:{java_version}-jre@")
    assert manifest.runtime.command[0] == "java"
    assert manifest.runtime.run_as == "${input.runtime_uid}:${input.runtime_gid}"
    assert manifest.runtime.read_only_root is True
    assert len(manifest.sources) == 1


def test_allay_uses_the_shaded_stable_release(
    manifests: dict[str, Manifest],
) -> None:
    manifest = manifests["allay"]
    source = manifest.sources[0]

    assert source.type == "github-release"
    assert isinstance(source.options, GitHubReleaseOptions)
    assert source.options.repository == "AllayMC/Allay"
    assert source.options.asset == "allay-server-*-shaded.jar"
    assert manifest.runtime.ports[0].protocol == "udp"
    assert manifest.checks[-1].pattern == "Network interface started at"


def test_nukkit_variants_use_their_official_build_repositories(
    manifests: dict[str, Manifest],
) -> None:
    nukkit = manifests["nukkit"].sources[0]
    mot = manifests["nukkit-mot"].sources[0]

    assert isinstance(nukkit.options, MavenOptions)
    assert nukkit.options.repository == "https://repo.opencollab.dev/maven-snapshots"
    assert nukkit.options.version == "1.0-SNAPSHOT"
    assert isinstance(mot.options, JenkinsOptions)
    assert mot.options.base_url == "https://motci.cn"
    assert mot.options.job == "Nukkit-MOT/job/master"
    assert mot.options.artifact == "Nukkit-MOT-SNAPSHOT.jar"


def test_powernukkitx_skips_only_after_explicit_license_acceptance(
    manifests: dict[str, Manifest],
) -> None:
    manifest = manifests["powernukkitx"]
    inputs = {item.name: item for item in manifest.inputs}
    source = manifest.sources[0]

    assert inputs["accept_license"].required is True
    assert isinstance(source.options, GitHubReleaseOptions)
    assert source.options.asset == "powernukkitx.jar"
    assert "--skip-setup" in manifest.runtime.command
    assert "--accept-license" in manifest.runtime.command


def test_purpur_uses_the_official_download_api_and_eula_template(
    repository_root: Path,
    manifests: dict[str, Manifest],
) -> None:
    manifest = manifests["purpur"]
    source = manifest.sources[0]
    inputs = {item.name: item for item in manifest.inputs}

    assert isinstance(source.options, HttpOptions)
    assert source.options.url == (
        "https://api.purpurmc.org/v2/purpur/26.2/latest/download"
    )
    assert inputs["eula"].required is True
    assert manifest.runtime.ports[0].protocol == "tcp"
    assert (repository_root / "database/purpur/template/eula.txt.tmpl").read_text(
        encoding="utf-8"
    ) == "eula=${input.eula}\n"
