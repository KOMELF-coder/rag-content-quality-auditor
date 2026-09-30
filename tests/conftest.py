from pathlib import Path

import httpx
import pytest

from my_actor.fetching import Fetcher
from my_actor.url_policy import URLPolicy


class ByteStream(httpx.AsyncByteStream):
    def __init__(self, body):
        self.body = body

    async def __aiter__(self):
        for start in range(0, len(self.body), 1024):
            yield self.body[start : start + 1024]


def response(body=b"", status=200, mime="text/html", headers=None):
    if isinstance(body, str):
        body = body.encode()
    return httpx.Response(
        status, headers={"content-type": mime, **(headers or {})}, stream=ByteStream(body)
    )


async def public_dns(host, port):
    return ["93.184.216.34"]


async def no_sleep(seconds):
    return None


@pytest.fixture
def make_fetcher():
    def make(handler, resolver=public_dns):
        return Fetcher(
            URLPolicy("https://example.com", resolver),
            transport=httpx.MockTransport(handler),
            sleep=no_sleep,
        )

    return make


@pytest.fixture
def fixture_text():
    return lambda name: (Path(__file__).parent.parent / "fixtures" / name).read_text(
        encoding="utf-8"
    )
