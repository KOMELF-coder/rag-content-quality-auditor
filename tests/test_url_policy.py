import asyncio

import pytest

from my_actor.models import AuditError
from my_actor.url_policy import URLPolicy, is_public_ip, normalize_url


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "100.64.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "::",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "2002:7f00:1::",
        "64:ff9b::7f00:1",
    ],
)
def test_private(address):
    assert not is_public_ip(address)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com",
        "data:abc",
        "javascript:alert(1)",
        "https://user:pass@example.com",
        "https://example.com:8080",
        "https://example.com\\@localhost",
        "https://exa mple.com",
    ],
)
def test_invalid(url):
    with pytest.raises(AuditError):
        normalize_url(url)


def test_normalization():
    assert (
        normalize_url("HTTPS://EXAMPLE.COM:443/a/?b=2&utm_x=x&a=1&fbclid=x#test")
        == "https://example.com/a/?a=1&b=2"
    )
    assert (
        normalize_url("../guide?q=x", "https://example.com/docs/a")
        == "https://example.com/guide?q=x"
    )
    assert normalize_url("https://example.com/a") != normalize_url("https://example.com/a/")
    assert normalize_url("https://example.com/?a=2&a=1") == "https://example.com/?a=2&a=1"


@pytest.mark.parametrize(
    "addresses", [["10.0.0.1"], ["93.184.216.34", "127.0.0.1"], ["::ffff:192.168.1.1"]]
)
def test_unsafe_dns(addresses):
    async def resolver(host, port):
        return addresses

    with pytest.raises(AuditError, match="public"):
        asyncio.run(URLPolicy("https://example.com", resolver).validate("https://example.com"))


@pytest.mark.parametrize("host", ["localhost", "foo.localhost", "foo.local", "foo.internal"])
def test_local_alias(host):
    with pytest.raises(AuditError):
        asyncio.run(URLPolicy(f"http://{host}").validate(f"http://{host}"))


def test_public_and_host():
    async def resolver(host, port):
        return ["93.184.216.34", "2606:4700:4700::1111"]

    policy = URLPolicy("https://example.com", resolver)
    assert asyncio.run(policy.validate("https://example.com"))[1]
    with pytest.raises(AuditError, match="hostname"):
        asyncio.run(policy.validate("https://docs.example.com"))
