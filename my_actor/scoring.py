"""Six bounded formulas. See ARCHITECTURE.md for every term and threshold."""

import math

from .chunking import recommend_chunking
from .models import Page


def profile(page: Page) -> str:
    title = page.title.lower()
    if "faq" in title or "frequently asked" in title:
        return "faq"
    if page.word_count < 150 and page.internal_link_count >= 15:
        return "navigation_or_index"
    if page.word_count < 80:
        return "short_content"
    if page.code_block_count or "/docs/" in page.url or "/tutorial/" in page.url:
        return "documentation"
    if page.paragraph_count >= 2 and page.heading_count:
        return "article"
    return "unknown"


def score(page: Page) -> Page:
    page.page_profile = profile(page)
    if page.status != "audited":
        page.score_breakdown = dict.fromkeys(
            ("content", "structure", "cleanliness", "uniqueness", "metadata", "accessibility"), 0.0
        )
        return page
    content = 30 * min(1, math.log1p(page.word_count) / math.log1p(600))
    structure = (
        4 * bool(page.title)
        + 6 * min(page.heading_count / 3, 1)
        + 6 * min(page.paragraph_count / 4, 1)
        + 4 * min((page.list_count + page.table_count + page.code_block_count) / 2, 1)
        - min(page.heading_hierarchy_anomalies, 2)
    )
    # A navigation/footer allowance of 25% avoids penalizing normal website chrome.
    cleanliness = 15 * (1 - max(0, page.boilerplate_ratio - 0.25) / 0.75)
    uniqueness = {"unique": 15, "near_duplicate": 5, "exact_duplicate": 0, "not_checked": 7.5}[
        page.duplicate_status
    ]
    metadata = (
        4 * bool(page.title)
        + 2 * page.has_meta_description
        + 2 * page.has_canonical
        + 2 * page.has_json_ld
    )
    accessibility = {"ok": 10, "too_short": 7, "empty": 2, "likely_requires_javascript": 2}.get(
        page.content_status, 0
    )
    if page.content_status in {"empty", "likely_requires_javascript"}:
        content = min(content, 3)
        cleanliness = min(cleanliness, 5)
    page.score_breakdown = {
        name: round(max(0.0, float(value)), 2)
        for name, value in (
            ("content", content),
            ("structure", structure),
            ("cleanliness", cleanliness),
            ("uniqueness", uniqueness),
            ("metadata", metadata),
            ("accessibility", accessibility),
        )
    }
    page.rag_readiness_score = round(sum(page.score_breakdown.values()), 2)
    total = page.rag_readiness_score
    page.rag_readiness_level = (
        "excellent"
        if total >= 85
        else "good"
        if total >= 70
        else "mixed"
        if total >= 50
        else "poor"
    )
    page.rag_value = (
        "high"
        if page.word_count >= 200 and page.heading_count >= 2
        else "medium"
        if page.word_count >= 60
        else "low"
    )
    if (
        page.page_profile == "navigation_or_index"
        or page.content_status != "ok"
        or page.duplicate_status in {"exact_duplicate", "near_duplicate"}
    ):
        page.rag_value = "low"
    page.recommended_for_rag = (
        total >= 70
        and page.content_status == "ok"
        and page.word_count >= 60
        and page.duplicate_status in {"unique", "not_checked"}
        and page.page_profile != "navigation_or_index"
    )
    if page.word_count >= 200:
        page.reasons.append("Substantial main content detected.")
    if page.heading_count >= 2:
        page.reasons.append("Page has clear heading structure.")
    if page.duplicate_status == "unique":
        page.reasons.append("Content appears unique within this audit.")
    elif page.duplicate_status == "not_checked":
        page.issues.append("Duplicate detection disabled; uniqueness is unverified.")
    else:
        page.issues.append(
            "Exact duplicate of another document."
            if page.duplicate_status == "exact_duplicate"
            else "Near-duplicate of another document."
        )
        page.recommendations.append(
            "Review the representative document and exclude redundant content before embedding."
        )
    if page.boilerplate_ratio > 0.6:
        page.issues.append("High boilerplate ratio.")
        page.recommendations.append("Use a focused main-content extraction upstream.")
    if page.content_status == "likely_requires_javascript":
        page.issues.append("Very little server-rendered text; page likely requires JavaScript.")
        page.recommendations.append(
            "Use a browser-capable crawler upstream, then audit its dataset."
        )
    elif page.word_count < 60:
        page.issues.append("Little useful text was extracted.")
        page.recommendations.append("Review this short document before ingestion.")
    if page.heading_count == 0 and page.word_count >= 60:
        page.issues.append("No heading structure detected.")
        page.recommendations.append("Preserve section headings in the source content.")
    if page.recommended_for_rag:
        page.recommendations.append(
            "Include as a candidate and validate retrieval against representative questions."
        )
    elif not page.recommendations:
        page.recommendations.append("Review the score components before including this document.")
    for name in ("reasons", "issues", "recommendations"):
        setattr(page, name, list(dict.fromkeys(getattr(page, name))))
    recommend_chunking(page)
    return page
