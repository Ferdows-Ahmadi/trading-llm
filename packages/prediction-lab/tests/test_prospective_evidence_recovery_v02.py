from __future__ import annotations

import httpx

from prediction_lab import prospective_evidence_recovery_v02 as recovery


class FakeClient:
    def __init__(self, statuses: list[int]) -> None:
        self.statuses = list(statuses)
        self.calls = 0

    def get(self, *_args: object, **_kwargs: object) -> httpx.Response:
        self.calls += 1
        status = self.statuses.pop(0)
        return httpx.Response(status, request=httpx.Request("GET", "https://example.test"))


def test_recovery_v2_identity_and_transport_are_frozen() -> None:
    assert recovery.RECOVERY_V2_AMENDMENT_COMMIT == (
        "a4b8be56fbb7e5291c6d72c122f880609627e972"
    )
    assert recovery.RECOVERY_V1_RUN_ID == 34809802640
    assert recovery.DEFAULT_SHARD_COUNT == 4
    assert recovery.SHARD_STAGGER_SECONDS == 30.0
    assert recovery.GDELT_MINIMUM_INTERVAL_SECONDS == 24.0
    assert recovery.GDELT_RETRIES == 8
    assert recovery.GDELT_RETRY_BACKOFF_SECONDS == 5.0
    assert recovery.COMMON_CRAWL_TIMEOUT_SECONDS == 60.0
    assert recovery.COMMON_CRAWL_RETRIES == 8
    assert recovery.COMMON_CRAWL_RETRY_BACKOFF_SECONDS == 2.0
    assert recovery.COMMON_CRAWL_MINIMUM_INTERVAL_SECONDS == 1.0


def test_recovery_v1_artifact_identity_is_frozen() -> None:
    assert recovery.RECOVERY_V1_ARTIFACTS == {
        0: (
            10338413642,
            "b59800c3cc88653362499e30e344ab63d8e5c913a41fcf9104a5e49c7578887b",
        ),
        1: (
            10336931583,
            "13c57aaeb1f29aad7ddb71c5bd37e9b3ea8a8cdd2773f9dcae25fe55286d3be4",
        ),
        2: (
            10339211930,
            "9da6ce9cc67b2a494dd7ccdfbd86459f57a83cb9c1597a63f4a42b9850292695",
        ),
        3: (
            10339470819,
            "af72149ab8f4f4c198ee28c508f639d70bd8bb149c8e93f0b60404f17edaf66a",
        ),
    }


def test_paced_commoncrawl_retries_transient_response() -> None:
    client = FakeClient([503, 200])
    archive = recovery.PacedFastCommonCrawlClient(
        client=client,  # type: ignore[arg-type]
        retries=2,
        retry_backoff_seconds=0.0,
        minimum_interval_seconds=0.0,
    )

    response = archive._get("https://example.test")

    assert response.status_code == 200
    assert client.calls == 2
