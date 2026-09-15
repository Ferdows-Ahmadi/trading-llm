from __future__ import annotations

import json
from pathlib import Path

import pytest

from prediction_lab import prospective_polymarket_custody as base
from prediction_lab import prospective_polymarket_custody_keyset as keyset
from prediction_lab import prospective_polymarket_custody_keyset_v2 as v2


def test_v2_applies_keyset_only_cap_and_restores_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, int] = {}

    def fake_collect(
        client: object,
        *,
        output_directory: Path,
        code_commit: str,
    ) -> dict[str, object]:
        del client, code_commit
        observed["max_pages"] = base.MAX_PAGES
        output_directory.mkdir(parents=True)
        summary: dict[str, object] = {
            "pagination_mode": "gamma-markets-keyset-after_cursor"
        }
        (output_directory / "custody-summary.json").write_text(
            json.dumps(summary) + "\n",
            encoding="utf-8",
        )
        return summary

    monkeypatch.setattr(keyset, "collect_prospective_custody_keyset", fake_collect)
    original = base.MAX_PAGES
    output = tmp_path / "custody"

    summary = v2.collect_prospective_custody_keyset_v2(
        object(),  # type: ignore[arg-type]
        output_directory=output,
        code_commit="test-commit",
    )

    assert observed["max_pages"] == 1000
    assert base.MAX_PAGES == original == 100
    assert summary["keyset_max_pages"] == 1000
    assert (
        summary["keyset_safety_cap_amendment_commit"]
        == v2.KEYSET_SAFETY_CAP_AMENDMENT_COMMIT
    )
    frozen = json.loads((output / "custody-summary.json").read_text())
    assert frozen["keyset_max_pages"] == 1000


def test_v2_relabels_safety_limit_and_restores_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_collect(
        client: object,
        *,
        output_directory: Path,
        code_commit: str,
    ) -> dict[str, object]:
        del client, output_directory, code_commit
        assert base.MAX_PAGES == 1000
        raise base.ProspectiveCustodyError(
            "Gamma keyset pagination hit 100-page safety limit"
        )

    monkeypatch.setattr(keyset, "collect_prospective_custody_keyset", fake_collect)
    original = base.MAX_PAGES

    with pytest.raises(
        base.ProspectiveCustodyError,
        match="1000-page safety limit",
    ):
        v2.collect_prospective_custody_keyset_v2(
            object(),  # type: ignore[arg-type]
            output_directory=tmp_path / "custody",
            code_commit="test-commit",
        )

    assert base.MAX_PAGES == original == 100
