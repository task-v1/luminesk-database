from __future__ import annotations

from pathlib import Path

import pytest
from luminesk_cli.domain.errors import SecurityError

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
