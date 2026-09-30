from collections import Counter
from statistics import mean, median

from .models import Page, utc_now


def aggregate(
    pages: list[Page],
    *,
    mode: str,
    source: str,
    started_at: str,
    discovered: int,
    selected: int,
    request_count: int = 0,
    runtime_seconds: float = 0,
    warnings=(),
    ai_metadata=None,
) -> dict:
    audited = [p for p in pages if p.status == "audited"]
    recommended = [p for p in audited if p.recommended_for_rag]
    # Exclude duplicate clusters and navigation pages from aggregate quality weighting.
    weighted = [
        p
        for p in audited
        if p.duplicate_status in {"unique", "not_checked"}
        and p.page_profile != "navigation_or_index"
    ]
    issue_counts = Counter(issue for p in pages for issue in set(p.issues))
    statuses = Counter(p.status for p in pages)
    duplicates = Counter(p.duplicate_status for p in audited)
    components = (
        {
            key: round(mean(p.score_breakdown[key] for p in weighted), 2)
            for key in weighted[0].score_breakdown
        }
        if weighted
        else {}
    )
    return {
        "schema_version": "1.0",
        "mode": mode,
        "source": source,
        "domain": source if mode == "website" else None,
        "source_dataset": source if mode == "dataset" else None,
        "started_at": started_at,
        "finished_at": utc_now(),
        "pages_discovered": discovered,
        "pages_selected": selected,
        "pages_processed": len(pages),
        "pages_successfully_audited": len(audited),
        "pages_failed": statuses["failed"],
        "pages_skipped": statuses["skipped"],
        "recommended_pages": len(recommended),
        "low_value_pages": sum(p.rag_value == "low" for p in audited),
        "unique_pages": duplicates["unique"],
        "exact_duplicates": duplicates["exact_duplicate"],
        "near_duplicates": duplicates["near_duplicate"],
        "duplicates_not_checked": duplicates["not_checked"],
        "likely_js_pages": sum(p.content_status == "likely_requires_javascript" for p in audited),
        "estimated_corpus_tokens": sum(p.estimated_tokens for p in recommended),
        "estimated_analyzed_tokens": sum(p.estimated_tokens for p in audited),
        "overall_score": round(mean(p.rag_readiness_score for p in weighted), 2)
        if weighted
        else None,
        "score_breakdown": components,
        "score_denominator": len(weighted),
        "score_aggregation_method": "Unweighted mean of audited unique/not-checked pages, excluding navigation_or_index; null if none.",
        "average_analyzed_score": round(mean(p.rag_readiness_score for p in audited), 2)
        if audited
        else None,
        "median_analyzed_score": median(p.rag_readiness_score for p in audited)
        if audited
        else None,
        "top_issues": [
            {"issue": issue, "count": count}
            for issue, count in sorted(issue_counts.items(), key=lambda x: (-x[1], x[0]))[:10]
        ],
        "recommended_include_patterns": [],
        "recommended_exclude_patterns": [],
        "warnings": list(dict.fromkeys(warnings)),
        "request_count": request_count,
        "runtime_seconds": round(runtime_seconds, 3),
        "ai_metadata": ai_metadata or {},
        "billable_result_count": len(audited),
        "coverage": "Bounded audit of observed eligible URLs/rows; not exhaustive.",
    }
