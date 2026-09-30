"""Create and verify a small controlled Apify dataset for Cloud validation.

Usage (PowerShell):
    $env:APIFY_TOKEN="..."
    .\.venv\Scripts\python.exe scripts\create_test_dataset.py

The script creates an UNNAMED dataset on purpose. This avoids named-storage conflicts
and is sufficient because the Actor accepts a dataset ID. The dataset contains six rows:
- useful Markdown
- useful HTML
- exact duplicate
- near duplicate
- useful content without a URL
- unusable row

The script only prints success after it has:
1. created the dataset;
2. re-fetched it by ID;
3. pushed all six rows;
4. re-read the items by ID;
5. verified that exactly six rows are readable.

It never prints the API token.
"""

from __future__ import annotations

import asyncio
import os

from apify_client import ApifyClientAsync


BASE_GUIDE = (
    "# Installation guide\n\n"
    "Install the product with pip and create a dedicated virtual environment before adding "
    "application dependencies. Configure the API key through an environment variable rather "
    "than committing credentials to source control. Validate the configuration with a small "
    "test request before deploying the service. In production, separate development and "
    "production settings, rotate secrets regularly, record deployment changes, and monitor "
    "failed requests. The deployment checklist should verify dependency versions, network "
    "access, logging, health checks, rollback procedures, and alerting. When troubleshooting, "
    "start with configuration values and connectivity, then inspect application logs and the "
    "most recent deployment changes. Keep the procedure documented so another engineer can "
    "repeat the same installation and validation steps consistently."
)

NEAR_GUIDE = (
    "# Installation guide\n\n"
    "Install the product with pip and create a dedicated virtual environment before adding "
    "application dependencies. Configure the API key through an environment variable rather "
    "than committing credentials to source control. Validate the configuration with a small "
    "test request before deploying the service. In production, separate development and "
    "production settings, rotate secrets regularly, record deployment changes, and monitor "
    "failed requests. The deployment checklist should verify dependency versions, network "
    "access, logging, health checks, rollback procedures, alerting, and a final smoke test. "
    "When troubleshooting, start with configuration values and connectivity, then inspect "
    "application logs and recent deployment changes. Keep the procedure documented so another "
    "engineer can repeat the same installation and validation steps consistently."
)

ITEMS = [
    {
        "url": "https://example.com/docs/guide",
        "markdown": BASE_GUIDE,
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
        "markdown": BASE_GUIDE,
    },
    {
        "url": "https://example.com/docs/guide-v2",
        "markdown": NEAR_GUIDE,
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


async def retry_get(dataset_client, attempts: int = 5, delay: float = 0.5):
    """Re-fetch a just-created dataset, tolerating short control-plane propagation."""
    last = None
    for _ in range(attempts):
        try:
            last = await dataset_client.get()
        except Exception:
            last = None
        if last is not None:
            return last
        await asyncio.sleep(delay)
    return None


async def retry_list_items(dataset_client, attempts: int = 5, delay: float = 0.5):
    """Read items back, tolerating short metadata/data-plane propagation."""
    last_error = None
    for _ in range(attempts):
        try:
            result = await dataset_client.list_items(limit=20)
            return result.items
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(delay)
    if last_error is not None:
        raise last_error
    return []


async def main() -> None:
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise SystemExit(
            "APIFY_TOKEN is not set. Configure it in your local/Codex environment; "
            "do not paste the token into chat."
        )

    client = ApifyClientAsync(token=token)

    # Intentionally unnamed: the Actor only needs the dataset ID and unnamed test
    # storage avoids UI/name-collision issues. It can expire under normal Apify retention.
    created = await client.datasets().get_or_create()
    dataset_id = created.get("id")
    if not dataset_id:
        raise RuntimeError("Apify returned a dataset object without an ID.")

    dataset_client = client.dataset(dataset_id)

    verified = await retry_get(dataset_client)
    if verified is None:
        raise RuntimeError(
            "Apify returned a dataset ID, but the dataset could not be re-fetched by that ID. "
            "Check that APIFY_TOKEN belongs to the same Apify account/workspace and has dataset "
            "read/write permissions."
        )

    await dataset_client.push_items(ITEMS)

    readable_items = await retry_list_items(dataset_client)
    if len(readable_items) != len(ITEMS):
        raise RuntimeError(
            f"Dataset verification failed: expected {len(ITEMS)} readable rows, "
            f"got {len(readable_items)}."
        )

    # Final metadata check is informative only; list_items above is the source of truth.
    final_info = await retry_get(dataset_client)
    reported_count = final_info.get("itemCount") if final_info else None

    print("Dataset created and verified successfully.")
    print(f"Dataset ID: {dataset_id}")
    print(f"Readable items: {len(readable_items)}")
    print(f"Reported item count: {reported_count}")
    print("Expected test rows: 6")


if __name__ == "__main__":
    asyncio.run(main())
