import asyncio
from types import SimpleNamespace

from conftest import response

from my_actor.apify_io import ApifySink
from my_actor.engine import Auditor
from my_actor.models import AuditError, AuditInput, Page
from my_actor.reporting import diagnostic
from my_actor.scoring import score


def test_website_end_to_end(make_fetcher, fixture_text):
    def handler(req):
        path = req.url.path
        if path == "/robots.txt":
            return response("User-agent: *\nDisallow: /blocked", mime="text/plain")
        if path == "/sitemap.xml":
            return response(
                "<urlset>"
                + "".join(
                    f"<url><loc>https://example.com/{p}</loc></url>"
                    for p in ("docs", "duplicate", "spa", "missing", "blocked")
                )
                + "</urlset>",
                mime="application/xml",
            )
        if path in {"/", "/docs", "/duplicate"}:
            return response(fixture_text("docs.html"))
        if path == "/spa":
            return response(fixture_text("spa.html"))
        return response(status=404)

    async def run():
        config = AuditInput(start_url="https://example.com", max_pages=6, check_ai_metadata=False)
        async with make_fetcher(handler) as f:
            auditor = Auditor(config)
            r = await auditor.website(f)
            assert r["pages_processed"] == 6
            assert r["pages_successfully_audited"] == 4
            assert r["exact_duplicates"] == 2
            assert r["likely_js_pages"] == 1
            assert r["pages_failed"] == r["pages_skipped"] == 1
            assert r["recommended_pages"] == 1

    asyncio.run(run())


def test_depth_zero_and_page_limit(make_fetcher):
    def handler(req):
        if req.url.path == "/robots.txt":
            return response("", status=404)
        return response('<main><p>hello</p><a href="/next">Next</a></main>')

    async def run():
        async with make_fetcher(handler) as f:
            r = await Auditor(
                AuditInput(start_url="https://example.com", max_depth=0, check_ai_metadata=False)
            ).website(f)
            assert r["pages_selected"] == 1 and r["request_count"] == 2

    asyncio.run(run())


def test_dataset_mixed():
    async def rows():
        for i, row in enumerate(
            [{"text": "Useful contents " * 30}, {}, {"html": "<main>Short answer.</main>"}]
        ):
            yield i, row

    async def run():
        auditor = Auditor(AuditInput(mode="dataset", dataset_id="src"))
        r = await auditor.dataset(rows(), total=3)
        assert r["pages_successfully_audited"] == 2
        assert r["pages_skipped"] == 1 and r["request_count"] == 0

    asyncio.run(run())


class FakeActor:
    def __init__(self, budget=10):
        self.budget = budget
        self.events = []
        self.values = {}

    def get_charging_manager(self):
        return self

    def compute_push_data_limit(self, **kwargs):
        return min(1, self.budget)

    async def push_data(self, data, *, charged_event_name):
        self.events.append((data, charged_event_name))
        self.budget -= 1
        return SimpleNamespace(charged_count=1, event_charge_limit_reached=self.budget == 0)

    async def set_value(self, key, value):
        self.values[key] = value


def test_ppe_events_and_budget():
    async def run():
        actor = FakeActor(budget=2)
        sink = ApifySink(actor)
        assert await sink.emit(score(Page(word_count=100)))
        assert await sink.emit(diagnostic("", AuditError("timeout", "timeout")))
        assert await sink.emit(score(Page(duplicate_status="exact_duplicate")))
        assert not await sink.emit(score(Page()))
        assert len(actor.events) == 2
        assert all(event == "page-audited" for _, event in actor.events)
        assert len(sink.diagnostics) == 1
        assert sink.charged_count == 2

    asyncio.run(run())


def test_engine_budget_reconciliation():
    async def rows():
        for i in range(3):
            yield i, {"text": "Useful content " * 20}

    async def run():
        sink = ApifySink(FakeActor(budget=1))
        auditor = Auditor(AuditInput(mode="dataset", dataset_id="test"), sink.emit)
        report = await auditor.dataset(rows(), total=3)
        await sink.finish(report)
        assert (
            report["pages_processed"]
            == report["billable_result_count"]
            == report["billing_event_requests"]
            == 1
        )
        assert report["warnings"]

    asyncio.run(run())


def test_entrypoint_rejects_existing_output(monkeypatch):
    from unittest.mock import AsyncMock, Mock

    import my_actor.main as entrypoint

    class ExistingOutputActor:
        log = Mock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get_input(self):
            return {"mode": "website", "start_url": "https://example.com"}

        async def open_dataset(self):
            return SimpleNamespace(
                get_metadata=AsyncMock(return_value=SimpleNamespace(item_count=1))
            )

    monkeypatch.setattr(entrypoint, "Actor", ExistingOutputActor())
    import pytest

    with pytest.raises(RuntimeError, match="fresh run"):
        asyncio.run(entrypoint.main())


def test_concurrency_preserves_order(make_fetcher):
    active = 0
    maximum = 0

    async def handler(req):
        nonlocal active, maximum
        if req.url.path == "/robots.txt":
            return response("User-agent: *\nAllow: /", mime="text/plain")
        if req.url.path == "/sitemap.xml":
            return response(
                "<urlset><url><loc>https://example.com/slow</loc></url><url><loc>https://example.com/fast</loc></url></urlset>",
                mime="text/xml",
            )
        active += 1
        maximum = max(active, maximum)
        await asyncio.sleep(0.02 if req.url.path == "/slow" else 0)
        active -= 1
        return response("<main><p>Identical useful contents.</p></main>")

    async def run():
        config = AuditInput(
            start_url="https://example.com/slow",
            max_pages=2,
            max_concurrency=2,
            check_ai_metadata=False,
        )
        async with make_fetcher(handler) as f:
            auditor = Auditor(config)
            await auditor.website(f)
            assert maximum == 2
            assert auditor.pages[0].source_id.endswith("/slow")
            assert auditor.pages[1].duplicate_of == "https://example.com/slow"

    asyncio.run(run())
