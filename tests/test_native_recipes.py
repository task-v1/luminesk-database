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
    assert manifest.ownership.preserve == ("config.toml",)
    assert manifest.template is None
    assert "server_name" not in {item.name for item in manifest.inputs}
    assert f"git fetch --depth 1 origin {DRAGONFLY_REVISION}" in dockerfile
    assert "-mod=readonly" in dockerfile
    assert "-buildvcs=false" in dockerfile


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
    assert "server_name" not in inputs
    assert manifest.template is None
    assert manifest.ownership.preserve == (
        "allowlist.json",
        "permissions.json",
        "server.properties",
        "valid_known_packs.json",
    )
    assert len(manifest.checks) == 1
    assert manifest.checks[0].kind == "log-regex"
    assert [port.protocol for port in manifest.runtime.ports] == ["udp", "udp"]
