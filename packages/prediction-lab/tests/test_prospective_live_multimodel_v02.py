from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx

from prediction_lab import prospective_live_enriched_v02 as evidence
from prediction_lab import prospective_live_multimodel_session_v02 as session
from prediction_lab import prospective_live_multimodel_v02 as selector


def _eligible(market_id: int, event_id: int) -> dict[str, object]:
    return {"market_id": str(market_id), "event_id": str(event_id)}


def test_multimodel_selector_is_event_unique_and_deterministic() -> None:
    rows = [_eligible(index, index // 2) for index in range(30)]
    first = selector.select_structural_candidates(rows)
    second = selector.select_structural_candidates(list(reversed(rows)))
    assert first == second
    assert len(first) == 12
    assert len({str(row["event_id"]) for row in first}) == 12


def test_visible_text_extraction_excludes_script_style_and_noscript() -> None:
    raw = (
        b"<html><style>hidden style</style><body>Hello <b>world</b>"
        b"<script>hidden script</script><noscript>hidden no script</noscript> end</body></html>"
    )
    text = evidence.extract_visible_text(raw, content_type="text/html", encoding="utf-8")
    assert "Hello world end" in text
    assert "hidden" not in text


def test_article_enrichment_failure_is_nonfatal_rss_fallback(tmp_path) -> None:
    raw_xml = b"""<?xml version='1.0' encoding='UTF-8'?>
    <rss><channel><item>
    <title>Relevant headline</title>
    <link>https://example.test/article</link>
    <source>Example</source>
    <pubDate>Wed, 16 Sep 2026 06:00:00 GMT</pubDate>
    <description>Useful frozen snippet</description>
    </item></channel></rss>"""

    class FakeRss:
        def search(self, question_text: str) -> tuple[bytes, str]:
            assert question_text == "Will X happen?"
            return raw_xml, "https://news.google.com/rss/search?q=x"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request)

    article_http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    article = evidence.ArticleEnricher(client=article_http)
    ticks = iter(
        [
            datetime(2026, 9, 16, 6, 10, tzinfo=UTC),
            datetime(2026, 9, 16, 6, 10, 1, tzinfo=UTC),
        ]
    )
    manifest = evidence.capture_question(
        question_id="polymarket-market:1",
        question_text="Will X happen?",
        output_directory=tmp_path,
        rss_client=FakeRss(),  # type: ignore[arg-type]
        article_client=article,
        clock=lambda: next(ticks),
    )
    assert manifest["status"] == "verified_complete"
    assert manifest["enrichment_attempts"] == 1
    assert manifest["enrichment_successes"] == 0
    evidence_dir = tmp_path / evidence._safe_name("polymarket-market:1")
    items = json.loads((evidence_dir / "evidence.json").read_text(encoding="utf-8"))
    assert "Useful frozen snippet" in items[0]["text"]
    assert items[0]["enrichment"]["enriched"] is False
    article.close()
    article_http.close()


def test_frozen_multimodel_identities_are_exact() -> None:
    assert session.MODEL_MANIFEST_SHA256 == (
        "296c91cbd22cd3d81b978f0c0a7499af8a54e9ecd8d76d20b8e6f2571691d40a"
    )
    assert session.FROZEN_MODELS == (
        (
            "llama3.1:8b",
            "sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e",
        ),
        (
            "qwen3.5:9b",
            "sha256:6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7",
        ),
        (
            "deepseek-r1:8b",
            "sha256:6995872bfe4c521a67b32da386cd21d5c6e819b6e0d62f79f64ec83be99f5763",
        ),
    )
    assert selector.TARGET_COHORT == 12
    assert session.ACQUISITION_SUCCESS_FLOOR == 10
