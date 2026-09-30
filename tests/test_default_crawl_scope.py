import asyncio
import json
import re
from pathlib import Path

import httpx
import pytest
from conftest import public_dns, response

from my_actor.discovery import Frontier
from my_actor.engine import Auditor
from my_actor.fetching import Fetcher
from my_actor.input_validation import validate_input
from my_actor.url_policy import URLPolicy

ROOT = Path(__file__).resolve().parents[1]


def suggested_input():
    schema = json.loads((ROOT / ".actor/input_schema.json").read_text())
    return {
        name: field.get("prefill", field["default"]) for name, field in schema["properties"].items()
    }


def test_suggested_form_matches_input_file_and_readme():
    suggested = suggested_input()
    example = json.loads((ROOT / ".actor/INPUT.json").read_text())
    assert validate_input(suggested) == validate_input(example)
    assert suggested["include_patterns"] == ["https://docs.python.org/3/tutorial/*"]
    assert suggested["max_pages"] == 8
    assert suggested["max_depth"] == 1
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    inputs = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", readme, re.DOTALL)]
    assert example in inputs


def test_start_url_is_eligible_in_suggested_scope():
    config = validate_input(suggested_input())
    frontier = Frontier(config, config.start_url)
    frontier.offer(config.start_url, 0)
    assert frontier.take(1) == [(config.start_url, 0)]


@pytest.mark.parametrize("source", ["sitemap", "links"])
@pytest.mark.parametrize(
    "restricted", [True, False], ids=["suggested-tutorial", "empty-whole-host"]
)
def test_suggested_scope_filters_discovery_before_selection(source, restricted):
    data = suggested_input()
    if not restricted:
        data["include_patterns"] = []
    config = validate_input(data)
    host = "https://docs.python.org"
    inside = host + "/3/tutorial/introduction.html"
    outside = [host + "/3.10/", host + "/3.11/", host + "/3.12/"]
    # More outside URLs than the page budget must not crowd out the tutorial page.
    outside += [host + f"/version-{index}/" for index in range(10)]
    fetched = []

    def handler(request):
        url = str(request.url)
        fetched.append(url)
        if request.url.path == "/robots.txt":
            return response("User-agent: *\nAllow: /", mime="text/plain")
        if request.url.path == "/sitemap.xml" and source == "sitemap":
            # Index and child sitemap are outside the content include pattern.
            return response(
                f"<sitemapindex><sitemap><loc>{host}/maps/pages.xml</loc></sitemap></sitemapindex>",
                mime="text/xml",
            )
        if request.url.path == "/maps/pages.xml":
            return response(
                "<urlset>"
                + "".join(f"<url><loc>{url}</loc></url>" for url in [*outside, inside])
                + "</urlset>",
                mime="text/xml",
            )
        if request.url.path in {"/sitemap.xml", "/llms.txt", "/llms-full.txt"}:
            return response(status=404)
        links = ""
        if url == config.start_url and source == "links":
            links = "".join(f'<a href="{target}">Page</a>' for target in [*outside, inside])
        return response(
            f"<main><h1>Documentation</h1><p>Useful documentation content.</p>{links}</main>"
        )

    async def run():
        async with Fetcher(
            URLPolicy(config.start_url, public_dns), transport=httpx.MockTransport(handler)
        ) as fetcher:
            auditor = Auditor(config)
            report = await auditor.website(fetcher)
        urls = [page.requested_url for page in auditor.pages]
        assert urls[0] == config.start_url
        if restricted:
            assert urls == [config.start_url, inside]
            assert report["pages_discovered"] == report["pages_selected"] == 2
            assert all(url.startswith(host + "/3/tutorial/") for url in urls)
            assert not set(outside).intersection(fetched)
        else:
            assert urls == [config.start_url, *outside[:7]]
            assert report["pages_selected"] == 8
            assert report["pages_discovered"] == len(outside) + 2
        if source == "sitemap":
            assert host + "/maps/pages.xml" in fetched

    asyncio.run(run())
