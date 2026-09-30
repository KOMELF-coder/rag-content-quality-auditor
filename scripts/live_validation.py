"""Manual, small public-site validation. Never imported by pytest."""

import argparse
import asyncio
import json
import logging
from pathlib import Path

from my_actor.engine import Auditor
from my_actor.input_validation import validate_input


async def run(args):
    data = (
        json.loads(Path(args.input).read_text(encoding="utf-8"))
        if args.input
        else {"mode": "website", "start_url": args.url, "max_pages": args.max_pages, "max_depth": 1}
    )
    config = validate_input(data)
    if config.mode != "website":
        raise ValueError("Live validation script audits public websites only.")
    auditor = Auditor(config)
    report = await auditor.website()
    destination = Path(args.output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "AUDIT_REPORT.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (destination / "pages.json").write_text(
        json.dumps([p.to_dict() for p in auditor.pages], indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="Actor JSON input file (overrides URL/page flags).")
    parser.add_argument("--url", default="https://docs.python.org/3/tutorial/")
    parser.add_argument("--max-pages", type=int, choices=range(1, 11), default=5)
    parser.add_argument("--output", default="validation-output/live")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run(parser.parse_args()))
