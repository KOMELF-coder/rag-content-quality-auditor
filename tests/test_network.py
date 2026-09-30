import asyncio
import gzip

import httpx
import pytest
from conftest import response

from my_actor.fetching import PinnedTransport
from my_actor.models import AuditError
from my_actor.robots import Robots
from my_actor.sitemap import discover_sitemaps, parse_sitemap


@pytest.mark.parametrize("status,count", [(404, 1), (403, 1), (429, 3), (500, 3)])
def test_http_retries(make_fetcher, status, count):
    async def run():
        async with make_fetcher(lambda req: response(status=status)) as fetcher:
            with pytest.raises(AuditError):
                await fetcher.fetch("https://example.com")
            assert fetcher.request_count == count

    asyncio.run(run())


def test_timeout(make_fetcher):
    def handler(req):
        raise httpx.ReadTimeout("test")

    async def run():
        async with make_fetcher(handler) as f:
            with pytest.raises(AuditError) as err:
                await f.fetch("https://example.com")
            assert err.value.code == "timeout"
            assert f.request_count == 3

    asyncio.run(run())


@pytest.mark.parametrize(
    "target", ["http://127.0.0.1/", "https://other.example.com/", "http://example.com/"]
)
def test_unsafe_redirect(make_fetcher, target):
    async def run():
        async with make_fetcher(
            lambda req: response(status=302, headers={"location": target})
        ) as f:
            with pytest.raises(AuditError):
                await f.fetch("https://example.com")
            assert f.request_count == 1

    asyncio.run(run())


def test_redirect_rechecks_dns(make_fetcher):
    calls = 0

    async def resolver(host, port):
        nonlocal calls
        calls += 1
        return ["93.184.216.34"] if calls == 1 else ["10.1.2.3"]

    async def run():
        async with make_fetcher(
            lambda req: response(status=302, headers={"location": "/private"}), resolver
        ) as f:
            with pytest.raises(AuditError) as err:
                await f.fetch("https://example.com")
            assert err.value.code == "blocked_by_ssrf_policy"
            assert f.request_count == 1

    asyncio.run(run())


def test_redirect_rechecks_robots(make_fetcher):
    def handler(req):
        if req.url.path == "/robots.txt":
            return response("User-agent: *\nDisallow: /private", mime="text/plain")
        return response(status=302, headers={"location": "/private"})

    async def run():
        async with make_fetcher(handler) as f:
            robots = Robots(f)
            with pytest.raises(AuditError) as err:
                await f.fetch("https://example.com/", guard=robots.guard)
            assert err.value.code == "robots_disallowed"
            assert f.request_count == 2

    asyncio.run(run())


def test_pinned_transport(make_fetcher):
    async def run():
        async with make_fetcher(lambda req: response()) as f:
            transport = PinnedTransport(f.policy, 1)

            def handle(req):
                assert req.url.host == "93.184.216.34"
                assert req.headers["host"] == "example.com"
                assert req.extensions["sni_hostname"] == "example.com"
                return response("ok")

            transport.transports["example.com"] = httpx.MockTransport(handle)
            async with httpx.AsyncClient(transport=transport) as client:
                assert (await client.get("https://example.com")).text == "ok"

    asyncio.run(run())


@pytest.mark.parametrize(
    "body,mime,headers,code",
    [
        (b"x", "application/pdf", {}, "unsupported_mime"),
        (b"x" * 100, "text/html", {}, "too_large"),
        (gzip.compress(b"x" * 1000), "text/html", {"content-encoding": "gzip"}, "too_large"),
        (b"x", "text/html", {"content-encoding": "br"}, "unsupported_encoding"),
    ],
)
def test_body_guards(make_fetcher, body, mime, headers, code):
    async def run():
        async with make_fetcher(lambda req: response(body, mime=mime, headers=headers)) as f:
            with pytest.raises(AuditError) as err:
                await f.fetch("https://example.com", limit=50)
            assert err.value.code == code

    asyncio.run(run())


@pytest.mark.parametrize(
    "body,status,allowed",
    [
        ("User-agent: *\nDisallow: /a", 200, False),
        ("User-agent: *\nAllow: /", 200, True),
        ("", 404, True),
        ("nonsense", 200, False),
        ("<html>error</html>", 200, False),
        ("", 503, False),
    ],
)
def test_robots(make_fetcher, body, status, allowed):
    async def run():
        async with make_fetcher(lambda req: response(body, status, "text/plain")) as f:
            robots = Robots(f)
            assert (await robots.rules("https://example.com/a")).allowed(
                "https://example.com/a"
            ) is allowed

    asyncio.run(run())


def test_sitemap_parsing():
    body = b"<urlset><url><loc>https://example.com/a</loc></url><url><loc>https://example.com/a</loc></url><url><loc>https://example.com/b</loc></url></urlset>"
    assert len(parse_sitemap(body)[1]) == 2
    assert parse_sitemap(body, 1)[2]
    assert parse_sitemap(gzip.compress(body))[1] == parse_sitemap(body)[1]


@pytest.mark.parametrize(
    "body", [b"<urlset>", b"<html/>", b'<!DOCTYPE a [<!ENTITY x "xx">]><urlset/>', b"\x00<urlset/>"]
)
def test_malformed_sitemap(body):
    with pytest.raises(AuditError):
        parse_sitemap(body)


def test_nested_sitemap(make_fetcher):
    def handler(req):
        if req.url.path == "/robots.txt":
            return response("User-agent: *\nAllow: /", mime="text/plain")
        if req.url.path == "/sitemap.xml":
            return response(
                "<sitemapindex><sitemap><loc>https://example.com/nested.xml</loc></sitemap></sitemapindex>",
                mime="application/xml",
            )
        return response(
            "<urlset><url><loc>https://example.com/a</loc></url></urlset>", mime="application/xml"
        )

    async def run():
        async with make_fetcher(handler) as f:
            urls, warnings = await discover_sitemaps(
                f, Robots(f), ["https://example.com/sitemap.xml"]
            )
            assert urls == ["https://example.com/a"]
            assert not warnings

    asyncio.run(run())
