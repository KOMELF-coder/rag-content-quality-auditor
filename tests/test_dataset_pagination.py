import asyncio
from types import SimpleNamespace

import pytest

from my_actor.dataset_input import SOURCE_FIELDS, source_rows
from my_actor.engine import Auditor
from my_actor.models import AuditInput
from my_actor.reporting import is_billable


class DatasetClient:
    def __init__(self, rows, response_cap=None):
        self.rows = rows
        self.response_cap = response_cap
        self.calls = []

    async def list_items(self, *, offset, limit, fields, clean):
        assert fields == SOURCE_FIELDS
        assert clean is False
        self.calls.append((offset, limit))
        count = min(limit, self.response_cap) if self.response_cap else limit
        return SimpleNamespace(items=self.rows[offset : offset + count])


@pytest.mark.parametrize(
    "size,limit,expected_calls",
    [
        (7, 100, [(0, 50), (7, 50)]),
        (120, 120, [(0, 50), (50, 50), (100, 20)]),
        (150, 73, [(0, 50), (50, 23)]),
        (0, 100, [(0, 50)]),
        (113, 200, [(0, 50), (50, 50), (100, 50), (113, 50)]),
        (1000, 1000, [(offset, 50) for offset in range(0, 1000, 50)]),
    ],
    ids=[
        "smaller-than-batch",
        "multiple-batches",
        "limit-inside-batch",
        "empty",
        "final-partial-batch",
        "thousand-rows",
    ],
)
def test_batched_rows_preserve_indexes(size, limit, expected_calls):
    rows = [{"text": f"Document {index}"} for index in range(size)]
    client = DatasetClient(rows)

    async def run():
        return [item async for item in source_rows(client, limit)]

    result = asyncio.run(run())
    assert result == list(enumerate(rows[:limit]))
    indexes = [index for index, _ in result]
    assert indexes == list(range(min(size, limit)))
    assert len(indexes) == len(set(indexes))
    assert client.calls == expected_calls
    assert all(offset + count <= limit for offset, count in client.calls)


def test_short_server_responses_do_not_skip_indexes():
    client = DatasetClient([{"text": str(index)} for index in range(125)], response_cap=17)

    async def run():
        return [index async for index, _ in source_rows(client, 110)]

    assert asyncio.run(run()) == list(range(110))
    assert [offset for offset, _ in client.calls] == [0, 17, 34, 51, 68, 85, 102]


def test_no_prefetch_after_consumer_stops():
    client = DatasetClient([{"text": "Content"}] * 100)

    async def run():
        generator = source_rows(client, 100)
        assert (await anext(generator))[0] == 0
        await generator.aclose()

    asyncio.run(run())
    assert client.calls == [(0, 50)]


def test_source_ids_and_mixed_row_billing_across_batches():
    rows = [
        {} if index in {0, 49, 50, 99, 100} else {"text": f"Document {index}: useful content."}
        for index in range(130)
    ]
    client = DatasetClient(rows)

    async def run():
        auditor = Auditor(AuditInput(mode="dataset", dataset_id="source", max_pages=107))
        report = await auditor.dataset(source_rows(client, 107), total=len(rows))
        assert [page.source_id for page in auditor.pages] == [
            f"dataset:source:{index}" for index in range(107)
        ]
        assert [index for index, page in enumerate(auditor.pages) if page.status == "skipped"] == [
            0,
            49,
            50,
            99,
            100,
        ]
        assert report["pages_processed"] == 107
        assert report["pages_skipped"] == 5
        assert report["pages_successfully_audited"] == report["billable_result_count"] == 102
        assert sum(is_billable(page) for page in auditor.pages) == 102

    asyncio.run(run())
    assert client.calls == [(0, 50), (50, 50), (100, 7)]
