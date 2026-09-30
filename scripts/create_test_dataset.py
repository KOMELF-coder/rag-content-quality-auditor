"""Create a small controlled Apify dataset for validating dataset mode in Cloud.

Usage:
    APIFY_TOKEN=... python scripts/create_test_dataset.py

The script creates a uniquely named dataset and pushes six rows covering:
- useful Markdown
- useful HTML
- exact duplicate
- near duplicate
- useful content without a URL
- unusable row

It prints only the dataset ID and basic metadata. It never prints the token.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from apify_client import ApifyClientAsync


ITEMS = [
    {
        "url": "https://example.com/docs/guide",
        "markdown": (
            "# Installation guide\n\n"
            "Install the product with pip. Then configure the API key in your environment. "
            "This guide explains setup, configuration, validation, and troubleshooting "
            "for a production deployment."
        ),
    },
    {
        "url": "https://example.com/docs/security",
        "html": """
<html>
  <head>
    <title>Security Guide</title>
    <meta name="description" content="Security configuration guide">
  </head>
  <body>
    <main>
      <h1>Security Guide</h1>
      <h2>Authentication</h2>
      <p>Use short-lived credentials and rotate secrets regularly.</p>
      <h2>Network security</h2>
      <p>Restrict access, validate inputs, and monitor failed requests.</p>
    </main>
  </body>
</html>
""".strip(),
    },
    {
        "url": "https://example.com/docs/guide-copy",
        "markdown": (
            "# Installation guide\n\n"
            "Install the product with pip. Then configure the API key in your environment. "
            "This guide explains setup, configuration, validation, and troubleshooting "
            "for a production deployment."
        ),
    },
    {
        "url": "https://example.com/docs/guide-v2",
        "markdown": (
            "# Installation guide\n\n"
            "Install the product with pip. Then configure the API key in your environment. "
            "This updated guide explains setup, configuration, validation, troubleshooting, "
            "and deployment checks for production environments."
        ),
    },
    {
        "markdown": (
            "# Internal knowledge article\n\n"
            "This row intentionally has no URL. It contains enough useful content to be "
            "analyzed and should still receive a stable dataset source ID."
        ),
    },
    {
        "url": "https://example.com/empty",
        "title": "Unusable row",
    },
]


async def main() -> None:
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise SystemExit(
            "APIFY_TOKEN is not set. Configure it in your local/Codex environment; "
            "do not paste the token into chat."
        )

    client = ApifyClientAsync(token=token)

    suffix = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = f"rag-auditor-test-{suffix}"

    dataset = await client.datasets().get_or_create(name=name)
    dataset_id = dataset["id"]
    dataset_client = client.dataset(dataset_id)

    await dataset_client.push_items(ITEMS)

    info = await dataset_client.get()
    item_count = info.get("itemCount") if info else None

    print("Dataset created successfully.")
    print(f"Dataset name: {name}")
    print(f"Dataset ID: {dataset_id}")
    print(f"Items pushed: {len(ITEMS)}")
    print(f"Reported item count: {item_count}")


if __name__ == "__main__":
    asyncio.run(main())
