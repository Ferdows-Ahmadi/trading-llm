"""Safety-cap-amended keyset recovery for prospective custody v0.1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from prediction_lab import prospective_polymarket_custody as base
from prediction_lab import prospective_polymarket_custody_keyset as keyset

KEYSET_SAFETY_CAP_AMENDMENT_COMMIT = "39c8d2b2486f4545624bb6bb88be364bd6d03225"
KEYSET_MAX_PAGES = 1000
_ORIGINAL_KEYSET_LIMIT_ERROR = "Gamma keyset pagination hit 100-page safety limit"


def collect_prospective_custody_keyset_v2(
    client: keyset.ProspectivePolymarketKeysetClient,
    *,
    output_directory: Path,
    code_commit: str,
) -> dict[str, object]:
    """Run keyset custody with only the frozen keyset safety ceiling amended."""
    original_max_pages = base.MAX_PAGES
    if original_max_pages != 100:
        raise base.ProspectiveCustodyError(
            f"Unexpected parent MAX_PAGES={original_max_pages}; expected frozen value 100"
        )

    base.MAX_PAGES = KEYSET_MAX_PAGES
    try:
        summary = keyset.collect_prospective_custody_keyset(
            client,
            output_directory=output_directory,
            code_commit=code_commit,
        )
    except base.ProspectiveCustodyError as exc:
        if str(exc) == _ORIGINAL_KEYSET_LIMIT_ERROR:
            raise base.ProspectiveCustodyError(
                f"Gamma keyset pagination hit {KEYSET_MAX_PAGES}-page safety limit"
            ) from exc
        raise
    finally:
        base.MAX_PAGES = original_max_pages

    summary["keyset_safety_cap_amendment_commit"] = (
        KEYSET_SAFETY_CAP_AMENDMENT_COMMIT
    )
    summary["keyset_max_pages"] = KEYSET_MAX_PAGES
    (output_directory / "custody-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args()

    with keyset.ProspectivePolymarketKeysetClient() as client:
        summary = collect_prospective_custody_keyset_v2(
            client,
            output_directory=args.output_directory,
            code_commit=args.code_commit,
        )

    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "snapshot_reference_at",
                    "gamma_pages",
                    "universe_rows",
                    "structurally_eligible_markets",
                    "event_representatives",
                    "clob_valid_event_representatives",
                    "clob_transport_failures",
                    "selected_rows",
                    "selected_event_groups",
                    "custody_adequate_for_forecaster_preregistration",
                    "keyset_max_pages",
                    "universe_sha256",
                    "selection_ledger_sha256",
                    "cohort_sha256",
                )
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
