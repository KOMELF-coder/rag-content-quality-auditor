import asyncio
import logging

from apify import Actor

from .apify_io import ApifySink
from .dataset_input import source_rows
from .engine import Auditor
from .input_validation import validate_input


class ActorLogHandler(logging.Handler):
    """Forward business-layer progress to the SDK's configured console logger."""

    def emit(self, record):
        Actor.log.log(record.levelno, record.getMessage())


async def main():
    async with Actor:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        project_log = logging.getLogger("my_actor")
        project_log.setLevel(logging.INFO)
        project_log.handlers = [ActorLogHandler()]
        project_log.propagate = False
        config = validate_input(await Actor.get_input())
        output_dataset = await Actor.open_dataset()
        if (await output_dataset.get_metadata()).item_count:
            raise RuntimeError(
                "Output dataset already contains results. Start a fresh run to avoid duplicate publication and charges; V1 does not resume partial runs."
            )
        Actor.log.info(
            "Starting RAG content quality audit; mode=%s, max_pages=%s",
            config.mode,
            config.max_pages,
        )
        sink = ApifySink(Actor)
        auditor = Auditor(config, emit=sink.emit)
        if config.mode == "website":
            report = await auditor.website()
        else:
            client = Actor.apify_client.dataset(config.dataset_id)
            info = await client.get()
            if info is None:
                raise ValueError("Source dataset is inaccessible or does not exist.")
            Actor.log.info("Source dataset accessible; available rows=%s", info.get("itemCount", 0))
            report = await auditor.dataset(
                source_rows(client, config.max_pages), total=info.get("itemCount")
            )
        await sink.finish(report)
        Actor.log.info(
            "Results saved in the default dataset; summary in AUDIT_REPORT; failures/skips in DIAGNOSTICS."
        )


if __name__ == "__main__":
    asyncio.run(main())
