from __future__ import annotations

import hashlib
import re
from datetime import UTC

from app.news_context.domain import NewsCandidate


def build_dedup_key(candidate: NewsCandidate) -> str:
    normalized_title = _normalize_text(candidate.title)
    normalized_source = _normalize_text(candidate.source_name)
    published_hour = candidate.published_at.astimezone(UTC).strftime("%Y%m%d%H")
    basis = f"{normalized_source}|{normalized_title}|{published_hour}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def _normalize_text(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value.strip().lower())
    alnum = re.sub(r"[^a-z0-9 ]", "", collapsed)
    return alnum
