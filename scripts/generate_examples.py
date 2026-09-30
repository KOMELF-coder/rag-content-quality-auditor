"""Create honest illustrative outputs from checked-in synthetic fixtures."""

import asyncio
import json
from pathlib import Path

from my_actor.engine import Auditor
from my_actor.models import AuditInput

ROOT = Path(__file__).resolve().parents[1]


async def main():
    async def rows():
        for i, name in enumerate(["docs.html", "docs.html", "spa.html"]):
            yield (
                i,
                {
                    "url": f"https://example.com/document-{i}",
                    "html": (ROOT / "fixtures" / name).read_text(encoding="utf-8"),
                },
            )

    auditor = Auditor(AuditInput(mode="dataset", dataset_id="synthetic-example"))
    report = await auditor.dataset(rows(), total=3)
    report["example_kind"] = "Illustrative synthetic fixtures; not a live benchmark."
    report["started_at"] = report["finished_at"] = "2026-09-30T00:00:00+00:00"
    report["runtime_seconds"] = 0
    destination = ROOT / "examples"
    destination.mkdir(exist_ok=True)
    for page in auditor.pages:
        page.collected_at = "2026-09-30T00:00:00+00:00"
    (destination / "page-results.json").write_text(
        json.dumps([p.to_dict() for p in auditor.pages], indent=2) + "\n", encoding="utf-8"
    )
    (destination / "AUDIT_REPORT.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: auditor.pages[0].to_dict()[k]
                for k in [
                    "rag_readiness_score",
                    "estimated_tokens",
                    "score_breakdown",
                    "recommended_for_rag",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
