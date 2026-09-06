from __future__ import annotations

from pathlib import Path

from luminesk_cli.domain.manifest import load_manifest

DRAGONFLY_REVISION = "a36ed0edb548298ab482939e1c653e39f9683719"


def test_dragonfly_build_is_pinned_and_reproducible(repository_root: Path) -> None:
    manifest = load_manifest(
        repository_root / "database" / "dragonfly" / "luminesk.toml"
    )
    dockerfile = (
        repository_root / "database" / "dragonfly" / ".luminesk" / "Dockerfile"
    ).read_text(encoding="utf-8")

    assert manifest.package.repository is not None
    assert manifest.package.repository.url == "https://github.com/df-mc/dragonfly"
    assert manifest.package.platforms == ("linux/amd64", "linux/arm64")
    assert manifest.sources == ()
    assert manifest.build is not None
    assert manifest.build.network is True
    assert manifest.build.output == "/out"
    assert manifest.runtime.image.startswith(
        "gcr.io/distroless/static-debian12:nonroot@sha256:"
    )
    assert manifest.ownership.executable == ("dragonfly",)
    assert f"git fetch --depth 1 origin {DRAGONFLY_REVISION}" in dockerfile
    assert "-mod=readonly" in dockerfile
    assert "-buildvcs=false" in dockerfile


def test_dragonfly_template_matches_runtime_paths(repository_root: Path) -> None:
    manifest = load_manifest(
        repository_root / "database" / "dragonfly" / "luminesk.toml"
    )
    template = (
        repository_root / "database" / "dragonfly" / "template" / "config.toml.tmpl"
    ).read_text(encoding="utf-8")

    assert manifest.ownership.preserve == ("config.toml",)
    assert 'Address = ":19132"' in template
    assert 'Name = "${input.server_name}"' in template
    assert manifest.checks[-1].kind == "process-alive"


def test_endstone_uses_the_official_pinned_runtime(repository_root: Path) -> None:
    manifest = load_manifest(
        repository_root / "database" / "endstone" / "luminesk.toml"
    )
    inputs = {item.name: item for item in manifest.inputs}

    assert manifest.package.platforms == ("linux/amd64",)
    assert manifest.package.repository is not None
    assert manifest.package.repository.url == "https://github.com/EndstoneMC/endstone"
    assert manifest.sources == ()
    assert manifest.runtime.image == (
        "endstone/endstone:0.11.10@sha256:"
        "299f3b987677d91d7e1d99f5273f725eadd2135428922aa587e443681d1ad277"
    )
    assert manifest.runtime.command == (
        "endstone",
        "--server-folder",
        "/server",
        "--yes",
    )
    assert manifest.runtime.run_as is None
    assert inputs["eula"].required is True
    assert [port.protocol for port in manifest.runtime.ports] == ["udp", "udp"]


def test_endstone_template_keeps_bedrock_ports_in_sync(
    repository_root: Path,
) -> None:
    template = (
        repository_root
        / "database"
        / "endstone"
        / "template"
        / "server.properties.tmpl"
    ).read_text(encoding="utf-8")

    assert "server-port=19132\n" in template
    assert "server-portv6=19133\n" in template
    assert "server-name=${input.server_name}\n" in template
