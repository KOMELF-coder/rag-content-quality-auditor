"""Exercise the real SDK/local storage with offline fixtures, one process per mode."""

import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx

from my_actor.engine import Auditor
from my_actor.fetching import Fetcher
from my_actor.models import AuditInput
from my_actor.url_policy import URLPolicy

ROOT = Path(__file__).resolve().parents[1]


class Stream(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data = data

    async def __aiter__(self):
        yield self.data


async def public_dns(host, port):
    return ["93.184.216.34"]


async def main(mode):
    from apify import Actor

    from my_actor.apify_io import ApifySink

    async with Actor:
        sink = ApifySink(Actor)
        auditor = Auditor(
            AuditInput(
                mode=mode,
                start_url="https://example.com",
                dataset_id="fixture",
                max_pages=3,
                max_depth=0,
                check_ai_metadata=False,
            ),
            sink.emit,
        )
        if mode == "website":

            def handler(req):
                body = (
                    b"User-agent: *\nAllow: /"
                    if req.url.path == "/robots.txt"
                    else (ROOT / "fixtures/docs.html").read_bytes()
                )
                return httpx.Response(
                    200,
                    headers={
                        "content-type": "text/plain"
                        if req.url.path == "/robots.txt"
                        else "text/html"
                    },
                    stream=Stream(body),
                )

            async with Fetcher(
                URLPolicy("https://example.com", public_dns), transport=httpx.MockTransport(handler)
            ) as fetcher:
                report = await auditor.website(fetcher)
        else:

            async def rows():
                yield (
                    0,
                    {
                        "markdown": "# Guide\n\n"
                        + "Prepare source documents before ingestion. " * 40
                    },
                )
                yield 1, {"html": (ROOT / "fixtures/docs.html").read_text()}
                yield 2, {}

            report = await auditor.dataset(rows(), total=3)
        await sink.finish(report)
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in (
                        "pages_processed",
                        "pages_successfully_audited",
                        "pages_skipped",
                        "billing_event_requests",
                        "platform_charged_event_count",
                    )
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["website", "dataset"], required=True)
    args = parser.parse_args()
    os.environ["APIFY_LOCAL_STORAGE_DIR"] = str(ROOT / "validation-output" / ("smoke-" + args.mode))
    asyncio.run(main(args.mode))
