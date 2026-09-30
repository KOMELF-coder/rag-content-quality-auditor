import xml.etree.ElementTree as ET
import zlib
from collections import deque
from io import BytesIO

from .fetching import TEXT_MIMES
from .limits import MAX_BODY_BYTES, MAX_SITEMAP_DEPTH, MAX_SITEMAP_URLS, MAX_SITEMAPS
from .models import AuditError
from .url_policy import normalize_url


def parse_sitemap(body: bytes, limit=MAX_SITEMAP_URLS) -> tuple[str, list[str], bool]:
    if body.startswith(b"\x1f\x8b"):
        try:
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            body = decoder.decompress(body, MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES or decoder.unconsumed_tail:
                raise AuditError("too_large", "Expanded sitemap exceeds size limit.")
            if not decoder.eof or decoder.unused_data:
                raise AuditError("malformed_sitemap", "Invalid gzip sitemap.")
        except zlib.error as exc:
            raise AuditError("malformed_sitemap", "Invalid gzip sitemap.") from exc
    if len(body) > MAX_BODY_BYTES:
        raise AuditError("too_large", "Sitemap exceeds size limit.")
    # Reject DTDs/entities and UTF-16/32 (NULs), keeping XML parsing non-expanding.
    if b"\x00" in body or b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise AuditError("malformed_sitemap", "DTD, entities and non-UTF-8 XML are unsupported.")
    urls = []
    seen = set()
    kind = None
    depth = 0
    try:
        for event, element in ET.iterparse(BytesIO(body), events=("start", "end")):
            tag = element.tag.rsplit("}", 1)[-1]
            if event == "start":
                depth += 1
                if depth > 32:
                    raise AuditError("malformed_sitemap", "XML nesting exceeds limit.")
                if kind is None:
                    kind = tag
                    if kind not in {"urlset", "sitemapindex"}:
                        raise AuditError(
                            "malformed_sitemap", "Expected a sitemap URL set or index."
                        )
            else:
                if tag == "loc" and element.text:
                    value = element.text.strip()
                    if value not in seen:
                        if len(urls) >= limit:
                            return kind, urls, True
                        seen.add(value)
                        urls.append(value)
                element.clear()
                depth -= 1
    except ET.ParseError as exc:
        raise AuditError("malformed_sitemap", "Sitemap XML cannot be parsed.") from exc
    return kind or "urlset", urls, False


async def discover_sitemaps(fetcher, robots, seeds: list[str]) -> tuple[list[str], list[str]]:
    pending = deque((url, 0) for url in seeds[:MAX_SITEMAPS])
    visited = set()
    pages = {}
    warnings = []
    while pending and len(visited) < MAX_SITEMAPS and len(pages) < MAX_SITEMAP_URLS:
        url, depth = pending.popleft()
        try:
            url = normalize_url(url)
            if url in visited:
                continue
            visited.add(url)
            result = await fetcher.fetch(url, guard=robots.guard, allowed_mimes=TEXT_MIMES)
            kind, locations, truncated = parse_sitemap(result.body, MAX_SITEMAP_URLS - len(pages))
            if truncated:
                warnings.append("Sitemap URL list truncated at the configured hard limit.")
            for location in locations:
                try:
                    target = normalize_url(location, result.final_url)
                    # Full DNS policy is applied before fetching; discard off-host discovery now.
                    from urllib.parse import urlsplit

                    if urlsplit(target).hostname != fetcher.policy.host:
                        continue
                except AuditError:
                    continue
                if kind == "sitemapindex":
                    if depth < MAX_SITEMAP_DEPTH and len(pending) + len(visited) < MAX_SITEMAPS:
                        pending.append((target, depth + 1))
                    else:
                        warnings.append("Nested sitemap traversal truncated at depth/file limit.")
                else:
                    pages.setdefault(target, None)
        except AuditError as exc:
            if exc.http_status != 404:
                warnings.append(f"Sitemap not used ({exc.code}).")
    if pending or len(pages) >= MAX_SITEMAP_URLS:
        warnings.append("Sitemap discovery reached a hard limit; coverage is partial.")
    return list(pages), list(dict.fromkeys(warnings))
