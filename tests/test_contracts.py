"""Contract drift guard: exported docs must match the code (re-run the scripts when this fails)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.export_contracts import CONTRACTS_DIR, build_contracts
from scripts.generate_parity_vectors import PARITY_DIR, build_vectors


@pytest.mark.parametrize(("relative", "content"), sorted(build_contracts().items()))
def test_exported_contracts_are_up_to_date(relative: str, content: str) -> None:
    path: Path = CONTRACTS_DIR / relative
    assert path.exists(), f"missing {relative}: run `python -m scripts.export_contracts`"
    assert path.read_text(encoding="utf-8") == content, f"{relative} is stale: run `python -m scripts.export_contracts`"


@pytest.mark.parametrize(("name", "content"), sorted(build_vectors().items()))
def test_parity_vectors_are_up_to_date(name: str, content: str) -> None:
    path: Path = PARITY_DIR / name
    assert path.exists(), f"missing {name}: run `python -m scripts.generate_parity_vectors`"
    assert path.read_text(encoding="utf-8") == content, (
        f"{name} is stale: run `python -m scripts.generate_parity_vectors`"
    )
