from __future__ import annotations

from pathlib import Path

from luminesk_cli.domain.manifest import GitHubReleaseOptions, load_manifest


def test_betteraltay_bundles_the_official_php_runtime(
    repository_root: Path,
) -> None:
    manifest = load_manifest(
        repository_root / "database" / "betteraltay" / "luminesk.toml"
    )
    core, php = manifest.sources

    assert manifest.package.platforms == ("linux/amd64",)
    assert manifest.package.repository is not None
    assert manifest.package.repository.url == (
        "https://github.com/BetterAltayBedrock/BetterAltay"
    )
    assert isinstance(core.options, GitHubReleaseOptions)
    assert core.options.repository == "BetterAltayBedrock/BetterAltay"
    assert core.options.asset == "BetterAltay.phar"
    assert core.target == "BetterAltay.phar"
    assert isinstance(php.options, GitHubReleaseOptions)
    assert php.options.repository == "Benedikt05/PHP-Binaries"
    assert php.options.version == "linux"
    assert php.options.asset == "bin.zip"
    assert php.target == "php-runtime"
    assert php.extract is True
    assert manifest.ownership.executable == ("php-runtime/bin/php7/bin/php",)
    assert manifest.runtime.image.startswith("ubuntu:22.04@sha256:")


def test_lunacy_uses_a_compatible_pinned_php_runtime(
    repository_root: Path,
) -> None:
    manifest = load_manifest(repository_root / "database" / "lunacy" / "luminesk.toml")
    source = manifest.sources[0]

    assert manifest.package.platforms == ("linux/amd64",)
    assert manifest.package.repository is not None
    assert manifest.package.repository.url == "https://github.com/karepanov35/Lunacy"
    assert isinstance(source.options, GitHubReleaseOptions)
    assert source.options.repository == "karepanov35/Lunacy"
    assert source.options.asset == "PocketMine-MP.phar"
    assert source.target == "PocketMine-MP.phar"
    assert manifest.runtime.image == (
        "pmmp/pocketmine-mp:5.44.3@sha256:"
        "58bc978b4ef951025d6fb03f5d95af118bb327b9fcb0438eb172c0bb2612ebb7"
    )
    assert manifest.runtime.command == (
        "/usr/bin/php",
        "PocketMine-MP.phar",
        "--no-wizard",
        "--enable-ansi",
    )


def test_php_recipes_keep_the_runtime_bounded(repository_root: Path) -> None:
    for name in ("betteraltay", "lunacy"):
        manifest = load_manifest(repository_root / "database" / name / "luminesk.toml")

        assert manifest.runtime.read_only_root is True
        assert manifest.runtime.run_as == "${input.runtime_uid}:${input.runtime_gid}"
        assert [(port.container, port.protocol) for port in manifest.runtime.ports] == [
            (19132, "udp")
        ]
        assert manifest.update.rollback_on_failure is True
