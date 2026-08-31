# This repository is not being distributed publicly until the release of version 2.0 of [Luminesk-CLI](https://github.com/task-v1/luminesk-cli)!

___

# Luminesk Database

[![Validate database](https://github.com/task-v1/luminesk-database/actions/workflows/validate.yml/badge.svg)](https://github.com/task-v1/luminesk-database/actions/workflows/validate.yml)

The official, Git-backed catalog of server cores and templates consumed by
[Luminesk CLI](https://github.com/task-v1/luminesk-cli). Every catalog entry is
an independent recipe rooted at `database/<name>/luminesk.toml`. A recipe may
also contain a template tree, but templates are optional.

## Repository layout

```text
database/
  <name>/
    luminesk.toml       # required recipe manifest
    template/           # optional files rendered into an instance
dist/
  index-v1.json         # bot-published immutable catalog snapshot
  index-v1.json.sha256  # checksum for the snapshot
schemas/                # public manifest and catalog contracts
tools/                  # validation and deterministic index generation
tests/                  # repository and CLI compatibility tests
```

The directory name must exactly match `[package].name`. Catalog entries are
sorted by that name and published with paths of the form
`database/<name>`. There is no fixed limit in the tests on how many recipes the
database may contain.

## Adding a core

1. Create `database/<name>/luminesk.toml`. Use a lowercase ASCII identifier for
   both the directory and `[package].name`.
2. Set a valid semantic `[package].version`, a non-empty summary, the game,
   edition, supported platforms, runtime, and at least one source, file, build,
   or template input required by the manifest contract.
3. Use only a production source type listed in
   [`schemas/supported-source-types-v1.json`](schemas/supported-source-types-v1.json).
   Official recipes cannot use `local-file` sources.
4. If the recipe needs rendered files, add a directory such as
   `database/<name>/template/` and declare `template = "template"` in the
   manifest. Omit both when the core has no template.
5. Add focused tests for behavior unique to the core. Shared catalog tests
   discover every recipe automatically; recipe-specific tests must select an
   entry by name rather than by its list position.
6. Open a pull request. Do not edit `dist/`; publication is handled after the
   content reaches `main`.

For an existing recipe, every change below `database/<name>/` other than a
README-only change must increase `[package].version`. New recipes do not need a
version relative to a previous catalog entry, but their initial version must be
valid SemVer.

The [Lumi recipe](database/lumi/luminesk.toml) is a complete example with an
optional template tree.

## Validation policy

CI loads every manifest with the tested Luminesk CLI, builds its canonical
recipe snapshot, and rejects unsafe or non-portable content. In particular,
official recipes cannot contain:

- symbolic links, hard links, or special files;
- binary archives such as ZIP, TAR, JAR, or executable library files;
- common secret and private-key file names or private-key material;
- an individual file larger than 16 MiB or a recipe tree larger than 64 MiB;
- `local-file` sources or paths that escape the recipe root.

Validation is static. It verifies manifests, templates, snapshots, catalog
metadata, and CLI compatibility; it does not boot Docker, download every remote
artifact, or prove that a server reaches readiness. Add a recipe-specific test
when a core needs stronger guarantees, and test the actual install and startup
before relying on it in production.

## Local checks

Python 3.13, [uv](https://docs.astral.sh/uv/), this repository, and a sibling
checkout of `luminesk-cli` are required. CI pins the CLI to an immutable commit
in both workflow files; use that same revision when reproducing CI exactly.

```bash
git -C ../luminesk-cli fetch origin 2.0
git -C ../luminesk-cli worktree add --detach ../luminesk-cli-ci \
  dae4f7bf3f9d90e940d164a1a7825b81c4b32085

uv sync --project ../luminesk-cli-ci --locked --extra dev --python 3.13

../luminesk-cli-ci/.venv/bin/python -m tools.validate --check-dist
../luminesk-cli-ci/.venv/bin/python -m tools.validate --base-ref origin/main
../luminesk-cli-ci/.venv/bin/python -m tools.build_index \
  --revision "$(git rev-parse HEAD)" --output /tmp/luminesk-catalog-check
../luminesk-cli-ci/.venv/bin/python -m ruff check tools tests
../luminesk-cli-ci/.venv/bin/python -m ruff format --check tools tests
MYPYPATH=../luminesk-cli-ci \
  ../luminesk-cli-ci/.venv/bin/python -m mypy tools tests
../luminesk-cli-ci/.venv/bin/python -m pytest

git -C ../luminesk-cli worktree remove ../luminesk-cli-ci
```

During development, `--check-dist` verifies the currently published index and
checksum. It intentionally does not require a pull request to regenerate the
index for unmerged recipe changes.

## CI and publication

`Validate database` runs for every pull request and push to `main`. It checks
all recipes, the existing published artifacts, version bumps, deterministic
catalog generation, formatting, types, and the compatibility test suite.

`Publish catalog index` runs only for content pushes to `main`. It repeats
source validation and compatibility tests, builds `dist/index-v1.json` for the
exact content commit, validates the generated index and checksum, and pushes a
`chore(catalog): ...` commit as `github-actions[bot]`. That commit is excluded
from another publication pass.

Both workflows use the same immutable Luminesk CLI revision. Updating the CLI
compatibility baseline is a deliberate change: update the two pinned revisions
together and run the full suite before merging.

The catalog revision identifies the complete published snapshot, but update
decisions are entry-local. The CLI compares the installed recipe's name, path,
version, manifest digest, and optional template digest with that entry in the
current index. Publishing or changing one core therefore does not make another
core outdated. If an entry itself changes, the CLI fetches that entry from the
new catalog revision.

## License

GPL-3.0. See [LICENSE](LICENSE).
