from .models import AuditError, Page
from .scoring import score

SKIPPED_CODES = {
    "unsupported_mime",
    "unsupported_encoding",
    "robots_disallowed",
    "off_host",
    "blocked_by_ssrf_policy",
    "invalid_url",
    "excluded_by_pattern",
    "dataset_row_unusable",
    "too_large",
}


def diagnostic(url: str, error: AuditError, *, source_type="website", source_id="") -> Page:
    page = Page(
        source_type=source_type,
        source_id=source_id,
        url=url,
        requested_url=url,
        status="skipped" if error.code in SKIPPED_CODES else "failed",
        error_code=error.code,
        http_status=error.http_status,
        content_status="unsupported" if error.code == "unsupported_mime" else "unavailable",
        issues=[str(error)],
        recommendations=["Review the diagnostic and fix or exclude this resource upstream."],
    )
    return score(page)


def is_billable(page: Page) -> bool:
    return page.status == "audited" and len(page.score_breakdown) == 6
