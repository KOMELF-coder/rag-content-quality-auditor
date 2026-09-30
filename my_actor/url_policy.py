"""URL normalization and conservative public-network policy."""

import asyncio
import ipaddress
import re
import socket
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from .limits import DNS_TIMEOUT_SECS
from .models import AuditError

TRACKING = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "_ga", "_gl"}


def normalize_url(value: str, base: str | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise AuditError("invalid_url", "URL is missing or too long.")
    if re.search(r"[\x00-\x20\x7f\\]", value):
        raise AuditError("invalid_url", "URL contains whitespace or forbidden characters.")
    try:
        parts = urlsplit(urljoin(base, value) if base else value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            raise ValueError()
        if parts.username is not None or parts.password is not None:
            raise ValueError()
        host = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        if "%" in host or not host:
            raise ValueError()
        port = parts.port
        if port not in (None, 80, 443):
            raise ValueError()
        authority = f"[{host}]" if ":" in host else host
        if port and (parts.scheme.lower(), port) not in {("http", 80), ("https", 443)}:
            authority += f":{port}"
        # Stable sorting preserves order for repeated values of the same key.
        query = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in TRACKING
        ]
        query.sort(key=lambda item: item[0])
        return urlunsplit(
            (parts.scheme.lower(), authority, parts.path or "/", urlencode(query), "")
        )
    except (ValueError, UnicodeError) as exc:
        raise AuditError(
            "invalid_url", "Expected a public HTTP(S) URL on port 80 or 443 without credentials."
        ) from exc


def is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return is_public_ip(str(address.ipv4_mapped))
        # No transition tunnels or translation prefixes with ambiguous routing.
        if address.sixtofour or address.teredo or address in ipaddress.ip_network("64:ff9b::/96"):
            return False
    return address.is_global and not (address.is_multicast or address.is_reserved)


async def resolve_host(host: str, port: int) -> list[str]:
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        entries = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return sorted({entry[4][0] for entry in entries})


class URLPolicy:
    def __init__(self, start_url: str, resolver=resolve_host):
        self.start_url = normalize_url(start_url)
        self.host = urlsplit(self.start_url).hostname
        self.resolver = resolver

    async def validate(self, url: str) -> tuple[str, list[str]]:
        url = normalize_url(url)
        parts = urlsplit(url)
        host = parts.hostname
        if host != self.host:
            raise AuditError("off_host", "URL is outside the starting hostname.")
        if host == "localhost" or host.endswith(
            (".localhost", ".local", ".internal", ".home", ".lan")
        ):
            raise AuditError("blocked_by_ssrf_policy", "Local hostnames are not allowed.")
        try:
            addresses = await asyncio.wait_for(
                self.resolver(host, parts.port or (443 if parts.scheme == "https" else 80)),
                timeout=DNS_TIMEOUT_SECS,
            )
        except (OSError, TimeoutError) as exc:
            raise AuditError("dns_error", "Hostname could not be resolved safely.") from exc
        if not addresses or not all(is_public_ip(address) for address in addresses):
            raise AuditError(
                "blocked_by_ssrf_policy", "Every resolved destination must be a public address."
            )
        return url, addresses
