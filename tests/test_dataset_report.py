import asyncio
from types import SimpleNamespace

import pytest

from my_actor.aggregation import aggregate
from my_actor.dataset_input import adapt_row, source_rows
from my_actor.models import AuditError, Page
from my_actor.reporting import diagnostic, is_billable
from my_actor.scoring import score


@pytest.mark.parametrize("field", ["markdown", "cleanText", "text", "content", "html"])
def test_fields(field):
    content = (
        "<main><p>Useful document content.</p></main>"
        if field == "html"
        else "# Document\n\nUseful content about preparing a document collection for retrieval."
    )
    result = adapt_row({field: content, "loadedUrl": "https://example.com/a"}, 0, "source")
    assert result.text and result.page.url == "https://example.com/a"


def test_precedence():
    result = adapt_row(
        {
            "markdown": "# A meaningful cleaned document with enough content to select.",
            "html": "<h1>Unwanted HTML</h1>",
        },
        0,
        "src",
    )
    assert "cleaned" in result.text
    result = adapt_row(
        {"markdown": " ", "text": "Meaningful text " * 10, "html": "<p>other</p>"}, 1, "src"
    )
    assert result.text.startswith("Meaningful")


def test_missing_url():
    result = adapt_row({"text": "Useful document content"}, 4, "src")
    assert result.page.source_id == "dataset:src:4"
    assert result.page.url == "" and result.page.issues


@pytest.mark.parametrize(
    "row",
    [{}, {"text": " "}, {"text": {"nested": "bad"}}, {"html": "<script>bad()</script>"}, None],
)
def test_unusable(row):
    with pytest.raises(AuditError) as err:
        adapt_row(row, 0, "src")
    assert err.value.code == "dataset_row_unusable"


def test_empty_and_bounded_dataset():
    class Client:
        async def list_items(self, **kwargs):
            return SimpleNamespace(items=[{"text": "hello"}] if kwargs["offset"] < 3 else [])

    async def run():
        assert len([r async for r in source_rows(Client(), 2)]) == 2
        assert len([r async for r in source_rows(Client(), 10)]) == 3

    asyncio.run(run())


@pytest.mark.parametrize("status", ["ok", "too_short", "empty", "likely_requires_javascript"])
def test_success_is_billable(status):
    assert is_billable(score(Page(content_status=status)))


@pytest.mark.parametrize(
    "code",
    [
        "invalid_url",
        "robots_disallowed",
        "unsupported_mime",
        "timeout",
        "dataset_row_unusable",
        "http_404",
    ],
)
def test_failure_not_billable(code):
    assert not is_billable(diagnostic("https://example.com", AuditError(code, code)))


def test_report_reconciles():
    pages = [
        score(
            Page(word_count=600, heading_count=3, paragraph_count=4, title="Title", list_count=2)
        ),
        score(Page(duplicate_status="exact_duplicate")),
        diagnostic("", AuditError("timeout", "Timeout")),
        diagnostic("", AuditError("robots_disallowed", "Blocked")),
    ]
    r = aggregate(
        pages, mode="website", source="example.com", started_at="test", discovered=4, selected=4
    )
    assert (
        r["pages_processed"]
        == r["pages_successfully_audited"] + r["pages_failed"] + r["pages_skipped"]
        == 4
    )
    assert r["billable_result_count"] == r["pages_successfully_audited"] == 2
    assert r["unique_pages"] + r["exact_duplicates"] + r["near_duplicates"] == 2
    assert r["score_denominator"] == 1
    assert r["recommended_pages"] <= r["pages_successfully_audited"]
    assert is_billable(pages[1])


def test_empty_report():
    report = aggregate(
        [], mode="dataset", source="empty", started_at="test", discovered=0, selected=0
    )
    assert report["overall_score"] is None
    assert report["billable_result_count"] == 0
