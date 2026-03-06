from datetime import UTC, datetime

from app.news_context.deduplication import build_dedup_key
from app.news_context.domain import NewsCandidate


def test_dedup_key_stable_for_equivalent_titles() -> None:
    candidate_a = NewsCandidate(
        external_id="a",
        source_name="Alpha Source",
        title="BTC rallies on ETF optimism",
        summary="Summary",
        url="https://example.com/1",
        published_at=datetime(2026, 1, 1, 12, 20, tzinfo=UTC),
    )
    candidate_b = NewsCandidate(
        external_id="b",
        source_name="Alpha Source",
        title="BTC   rallies on ETF optimism!!!",
        summary="Different summary",
        url="https://example.com/2",
        published_at=datetime(2026, 1, 1, 12, 55, tzinfo=UTC),
    )

    assert build_dedup_key(candidate_a) == build_dedup_key(candidate_b)
