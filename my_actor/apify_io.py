"""Apify-only persistence and PPE adapter."""

from .limits import EVENT_NAME
from .reporting import is_billable


class ApifySink:
    def __init__(self, actor):
        self.actor = actor
        self.diagnostics = []
        self.event_requests = 0
        self.charged_count = 0

    async def emit(self, page) -> bool:
        if not is_billable(page):
            # Diagnostics in KVS avoid synthetic dataset-item events for failures.
            self.diagnostics.append(page.to_dict())
            return True
        manager = self.actor.get_charging_manager()
        if (
            manager.compute_push_data_limit(
                items_count=1, event_name=EVENT_NAME, is_default_dataset=True
            )
            < 1
        ):
            return False
        result = await self.actor.push_data(page.to_dict(), charged_event_name=EVENT_NAME)
        self.event_requests += 1
        self.charged_count += result.charged_count
        return True

    async def finish(self, report):
        report["billing_event_name"] = EVENT_NAME
        report["billing_event_requests"] = self.event_requests
        report["platform_charged_event_count"] = self.charged_count
        report["billing_note"] = (
            "Eligibility and requested events are distinct from platform charges. Local/non-PPE runs do not charge customers."
        )
        await self.actor.set_value("DIAGNOSTICS", self.diagnostics)
        await self.actor.set_value("AUDIT_REPORT", report)
