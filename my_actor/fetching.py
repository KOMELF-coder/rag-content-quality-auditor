"""Bounded HTTP transport. No automatic redirects or unbounded decompression."""

import asyncio
import logging
import ssl
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx

from .limits import MAX_BODY_BYTES, MAX_REDIRECTS, MAX_RETRIES, MAX_RETRY_WAIT, USER_AGENT
from .models import AuditError
from .url_policy import URLPolicy, normalize_url

log = logging.getLogger(__name__)
PAGE_MIMES = {"text/html", "application/xhtml+xml", "text/plain", "text/markdown"}
TEXT_MIMES = PAGE_MIMES | {"application/xml", "text/xml", "application/gzip", "application/x-gzip"}


class PinnedTransport(httpx.AsyncBaseTransport):
    """Each socket uses a validated numeric address, with original Host and TLS SNI.

    A separate underlying connection pool per hostname prevents cross-host TLS reuse.
    HTTP proxy environment variables are intentionally ignored.
    """

    def __init__(self, policy: URLPolicy, concurrency: int):
        self.policy = policy
        self.concurrency = concurrency
        self.transports: dict[str, httpx.AsyncHTTPTransport] = {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        _, addresses = await self.policy.validate(str(request.url))
        host = request.url.host
        if host not in self.transports:
            self.transports[host] = httpx.AsyncHTTPTransport(
                verify=ssl.create_default_context(),
                retries=0,
                limits=httpx.Limits(
                    max_connections=self.concurrency, max_keepalive_connections=self.concurrency
                ),
            )
        headers = request.headers.copy()
        headers.pop("cookie", None)
        headers["Host"] = request.url.netloc.decode("ascii")
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=addresses[0]),
            headers=headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": host},
        )
        return await self.transports[host].handle_async_request(pinned)

    async def aclose(self):
        for transport in self.transports.values():
            await transport.aclose()


@dataclass
class FetchResult:
    requested_url: str
    final_url: str
    status: int
    mime: str
    body: bytes
    encoding: str = "utf-8"

    @property
    def text(self) -> str:
        try:
            return self.body.decode(self.encoding, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


def retry_delay(value: str | None, attempt: int) -> float:
    try:
        delay = float(value) if value else 2**attempt
    except ValueError:
        try:
            delay = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            delay = 2**attempt
    return max(0.0, min(delay, MAX_RETRY_WAIT))


async def bounded_body(response: httpx.Response, limit: int) -> bytes:
    encoding = response.headers.get("content-encoding", "identity").lower().strip()
    if encoding not in {"identity", "", "gzip", "deflate"}:
        raise AuditError("unsupported_encoding", "Unsupported response compression.")
    length = response.headers.get("content-length", "")
    if length.isdigit() and int(length) > limit:
        raise AuditError("too_large", "Response exceeds the body size limit.")
    decompressor = (
        zlib.decompressobj(16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS)
        if encoding in {"gzip", "deflate"}
        else None
    )
    output = bytearray()
    transferred = 0
    try:
        async for chunk in response.aiter_raw():
            transferred += len(chunk)
            if transferred > limit:
                raise AuditError("too_large", "Compressed response exceeds the body size limit.")
            decoded = (
                decompressor.decompress(chunk, limit + 1 - len(output)) if decompressor else chunk
            )
            output.extend(decoded)
            if len(output) > limit or (decompressor and decompressor.unconsumed_tail):
                raise AuditError("too_large", "Decoded response exceeds the body size limit.")
        if decompressor and (not decompressor.eof or decompressor.unused_data):
            raise AuditError("invalid_encoding", "Incomplete or concatenated compressed response.")
    except zlib.error as exc:
        raise AuditError("invalid_encoding", "Invalid compressed response.") from exc
    return bytes(output)


class Fetcher:
    def __init__(
        self, policy: URLPolicy, *, concurrency=4, timeout=25, transport=None, sleep=asyncio.sleep
    ):
        self.policy = policy
        self.timeout = timeout
        self.sleep = sleep
        self.request_count = 0
        self.semaphore = asyncio.Semaphore(concurrency)
        self.client = httpx.AsyncClient(
            transport=transport or PinnedTransport(policy, concurrency),
            follow_redirects=False,
            trust_env=False,
            timeout=timeout,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Encoding": "identity",
                "Accept": "text/html,text/plain,application/xml;q=0.9,*/*;q=0.1",
            },
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def fetch(
        self, url: str, *, guard=None, allowed_mimes=PAGE_MIMES, limit=MAX_BODY_BYTES
    ) -> FetchResult:
        requested = normalize_url(url)
        current = requested
        visited = set()
        for _ in range(MAX_REDIRECTS + 1):
            current, _ = await self.policy.validate(current)
            if current in visited:
                raise AuditError("redirect_loop", "Redirect loop detected.")
            visited.add(current)
            if guard:
                await guard(current)
            for attempt in range(MAX_RETRIES + 1):
                try:
                    async with self.semaphore, asyncio.timeout(self.timeout):
                        self.request_count += 1
                        async with self.client.stream(
                            "GET", current, headers={"Cookie": ""}
                        ) as response:
                            status = response.status_code
                            if status in {301, 302, 303, 307, 308}:
                                location = response.headers.get("location")
                                if not location:
                                    raise AuditError(
                                        "invalid_redirect", "Redirect is missing Location.", status
                                    )
                                target = normalize_url(location, current)
                                if (
                                    urlsplit(current).scheme == "https"
                                    and urlsplit(target).scheme == "http"
                                ):
                                    raise AuditError(
                                        "unsafe_redirect", "HTTPS downgrade refused.", status
                                    )
                                current = target
                                break
                            if status in {429, 500, 502, 503, 504} and attempt < MAX_RETRIES:
                                delay = retry_delay(response.headers.get("retry-after"), attempt)
                            elif status >= 400:
                                code = "http_5xx" if status >= 500 else f"http_{status}"
                                raise AuditError(code, f"HTTP {status} response.", status)
                            elif not 200 <= status < 300:
                                raise AuditError(
                                    "http_unexpected", f"Unexpected HTTP {status}.", status
                                )
                            else:
                                mime = (
                                    response.headers.get("content-type", "")
                                    .split(";", 1)[0]
                                    .strip()
                                    .lower()
                                )
                                if mime not in allowed_mimes:
                                    raise AuditError(
                                        "unsupported_mime",
                                        "Response content type is not supported.",
                                        status,
                                    )
                                body = await bounded_body(response, limit)
                                return FetchResult(
                                    requested,
                                    current,
                                    status,
                                    mime,
                                    body,
                                    response.encoding or "utf-8",
                                )
                    log.warning(
                        "Retrying transient HTTP response (%s), attempt %s", status, attempt + 1
                    )
                    await self.sleep(delay)
                except (httpx.TimeoutException, TimeoutError) as exc:
                    if attempt == MAX_RETRIES:
                        raise AuditError("timeout", "Request deadline exceeded.") from exc
                    await self.sleep(2**attempt)
                except httpx.HTTPError as exc:
                    raise AuditError("network_error", "HTTP transport failed.") from exc
        raise AuditError("too_many_redirects", "Redirect limit reached.")
