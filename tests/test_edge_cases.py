import asyncio
import gzip
import json
from pathlib import Path

import httpx
import pytest
from conftest import response

from my_actor.dataset_input import adapt_row
from my_actor.discovery import Frontier
from my_actor.duplicates import DuplicateIndex
from my_actor.engine import Auditor
from my_actor.fetching import retry_delay
from my_actor.input_validation import validate_input
from my_actor.metadata import check_ai_files
from my_actor.models import AuditError, AuditInput, Page
from my_actor.robots import Robots
from my_actor.sitemap import discover_sitemaps, parse_sitemap


def test_redirect_loop(make_fetcher):
    async def run():
        async with make_fetcher(lambda req: response(status=302, headers={"location": "/"})) as f:
            with pytest.raises(AuditError) as err:
                await f.fetch("https://example.com")
            assert err.value.code == "redirect_loop"
            assert f.request_count == 1

    asyncio.run(run())


def test_redirect_limit(make_fetcher):
    def handler(req):
        index = int(req.url.path.strip("/") or "0")
        return response(status=302, headers={"location": f"/{index + 1}"})

    async def run():
        async with make_fetcher(handler) as f:
            with pytest.raises(AuditError) as err:
                await f.fetch("https://example.com/0")
            assert err.value.code == "too_many_redirects"
            assert f.request_count == 6

    asyncio.run(run())


def test_cookie_not_replayed(make_fetcher):
    def handler(req):
        assert not req.headers.get("cookie")
        return response("hello", headers={"set-cookie": "session=example; Path=/"})

    async def run():
        async with make_fetcher(handler) as f:
            await f.fetch("https://example.com/a")
            await f.fetch("https://example.com/b")

    asyncio.run(run())


def test_retry_success_and_wait(make_fetcher):
    count = 0
    delays = []

    def handler(req):
        nonlocal count
        count += 1
        return (
            response("hello")
            if count == 3
            else response(status=429, headers={"retry-after": "9999"})
        )

    async def sleep(delay):
        delays.append(delay)

    async def run():
        async with make_fetcher(handler) as f:
            f.sleep = sleep
            assert (await f.fetch("https://example.com")).text == "hello"
            assert delays == [10, 10]

    asyncio.run(run())


@pytest.mark.parametrize(
    "value", ["bad", "-5", "Wed, 21 Oct 2015 07:28:00 GMT", "99999", "nan", "inf"]
)
def test_retry_after_bounded(value):
    assert 0 <= retry_delay(value, 1) <= 10


def test_sitemap_expansion_limit():
    with pytest.raises(AuditError) as err:
        parse_sitemap(gzip.compress(b"x" * 2_000_001))
    assert err.value.code == "too_large"


def test_recursive_sitemap_bounded(make_fetcher):
    def handler(req):
        index = int(req.url.path.strip("/") or "0")
        return response(
            f"<sitemapindex><sitemap><loc>https://example.com/{index + 1}</loc></sitemap></sitemapindex>",
            mime="text/xml",
        )

    async def run():
        async with make_fetcher(handler) as f:
            urls, warnings = await discover_sitemaps(
                f, Robots(f, enabled=False), ["https://example.com/0"]
            )
            assert urls == [] and warnings
            assert f.request_count == 4

    asyncio.run(run())


def test_cyclic_sitemap(make_fetcher):
    async def run():
        async with make_fetcher(
            lambda req: response(
                "<sitemapindex><sitemap><loc>https://example.com/map</loc></sitemap></sitemapindex>",
                mime="text/xml",
            )
        ) as f:
            await discover_sitemaps(f, Robots(f, enabled=False), ["https://example.com/map"])
            assert f.request_count == 1

    asyncio.run(run())


def test_llms_html_fallback_not_present(make_fetcher):
    async def run():
        async with make_fetcher(lambda req: response("<html>Not found</html>")) as f:
            result = await check_ai_files(f, Robots(f, enabled=False), "https://example.com")
            assert not result["llms_txt_present"]
            assert not result["llms_full_txt_present"]

    asyncio.run(run())


def test_globs_apply_to_redirect(make_fetcher):
    def handler(req):
        return response(status=302, headers={"location": "/private/"})

    async def run():
        cfg = AuditInput(
            start_url="https://example.com",
            max_depth=0,
            respect_robots_txt=False,
            check_ai_metadata=False,
            exclude_patterns=("https://example.com/private/*",),
        )
        async with make_fetcher(handler) as f:
            auditor = Auditor(cfg)
            result = await auditor.website(f)
            assert result["pages_skipped"] == 1
            assert auditor.pages[0].error_code == "excluded_by_pattern"
            assert f.request_count == 1

    asyncio.run(run())


def test_frontier_bounded():
    frontier = Frontier(AuditInput(), "https://example.com")
    for i in range(10002):
        frontier.offer(f"https://example.com/{i}", 1)
    assert len(frontier.seen) == len(frontier.queue) == 10000
    assert frontier.truncated


def test_duplicates_candidate_cap(monkeypatch):
    monkeypatch.setattr("my_actor.duplicates.simhash", lambda text: 123)
    idx = DuplicateIndex()
    # Different lengths avoid matches while placing every fingerprint in the same bands.
    for i in range(140):
        idx.apply(Page(source_id=str(i), word_count=100 * 2**i), f"different content {i}")
    assert idx.truncated
    assert all(len(bucket) <= 128 for bucket in idx.buckets.values())


def test_empty_dataset_end_to_end():
    async def rows():
        for i in []:
            yield i

    async def run():
        report = await Auditor(AuditInput(mode="dataset", dataset_id="empty")).dataset(
            rows(), total=0
        )
        assert report["pages_processed"] == 0 and report["warnings"]

    asyncio.run(run())


def test_no_html_scored_as_text():
    with pytest.raises(AuditError) as err:
        adapt_row({"text": "<script>" + "invisible code " * 10 + "</script>"}, 0, "src")
    assert err.value.code == "dataset_row_unusable"


def test_dataset_no_network(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Dataset analysis must not use HTTP.")

    monkeypatch.setattr(httpx.AsyncClient, "send", unexpected)
    assert adapt_row({"url": "http://127.0.0.1/private", "text": "Supplied content"}, 0, "src").text


def test_schema_defaults_match_runtime():
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / ".actor/input_schema.json").read_text()
    )
    defaults = {name: field["default"] for name, field in schema["properties"].items()}
    assert validate_input(defaults) == validate_input({})
