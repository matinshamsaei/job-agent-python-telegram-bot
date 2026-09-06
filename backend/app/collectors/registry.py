from collections.abc import Callable

import httpx

from app.collectors.ashby import AshbyCollector
from app.collectors.base import JobCollector
from app.collectors.greenhouse import GreenhouseCollector
from app.collectors.lever import LeverCollector
from app.collectors.personio import PersonioXmlCollector
from app.collectors.recruitee import RecruiteeCollector
from app.collectors.smartrecruiters import SmartRecruitersCollector
from app.collectors.teamtailor import TeamtailorCollector
from app.collectors.workable import WorkableCollector
from app.collectors.workday import WorkdayCollector
from app.core.config import Settings
from app.core.enums import AtsType, CollectionStrategy

CollectorFactory = Callable[[httpx.AsyncClient, Settings], JobCollector]

ADAPTERS: dict[str, CollectorFactory] = {
    AtsType.GREENHOUSE.value: GreenhouseCollector,
    AtsType.LEVER.value: LeverCollector,
    AtsType.PERSONIO_XML.value: PersonioXmlCollector,
    AtsType.ASHBY.value: AshbyCollector,
    AtsType.SMARTRECRUITERS.value: SmartRecruitersCollector,
    AtsType.WORKABLE.value: WorkableCollector,
    AtsType.RECRUITEE.value: RecruiteeCollector,
    AtsType.TEAMTAILOR.value: TeamtailorCollector,
    AtsType.WORKDAY.value: WorkdayCollector,
}

# ATS platforms we can recognise but cannot read yet. Sources pointing at these
# report `adapter_missing` instead of being silently skipped, so the coverage
# report shows exactly where the next adapter is worth building.
KNOWN_WITHOUT_ADAPTER: dict[str, str] = {
    AtsType.JOBVITE.value: "no stable public postings endpoint",
    AtsType.ICIMS.value: "no public API; portal is session-based",
    AtsType.COMEET.value: "public API requires a per-company token",
    AtsType.BAMBOOHR.value: "careers JSON varies per tenant",
    AtsType.TALEO.value: "legacy portal, no public JSON",
    AtsType.SUCCESSFACTORS.value: "OData API requires credentials",
    AtsType.CUSTOM.value: "bespoke careers API, needs per-company work",
    AtsType.CAREER_PAGE.value: "HTML careers page, needs browser extraction",
    AtsType.UNKNOWN.value: "ATS not identified yet",
}

STRATEGY_BY_ATS: dict[str, str] = {
    AtsType.GREENHOUSE.value: CollectionStrategy.API.value,
    AtsType.LEVER.value: CollectionStrategy.API.value,
    AtsType.PERSONIO_XML.value: CollectionStrategy.XML.value,
    AtsType.ASHBY.value: CollectionStrategy.API.value,
    AtsType.SMARTRECRUITERS.value: CollectionStrategy.API.value,
    AtsType.WORKABLE.value: CollectionStrategy.API.value,
    AtsType.RECRUITEE.value: CollectionStrategy.API.value,
    AtsType.TEAMTAILOR.value: CollectionStrategy.XML.value,
    AtsType.WORKDAY.value: CollectionStrategy.API.value,
    AtsType.JOBVITE.value: CollectionStrategy.HTML.value,
    AtsType.ICIMS.value: CollectionStrategy.BROWSER.value,
    AtsType.COMEET.value: CollectionStrategy.API.value,
    AtsType.BAMBOOHR.value: CollectionStrategy.JSON.value,
    AtsType.TALEO.value: CollectionStrategy.BROWSER.value,
    AtsType.SUCCESSFACTORS.value: CollectionStrategy.BROWSER.value,
    AtsType.CUSTOM.value: CollectionStrategy.HTML.value,
    AtsType.CAREER_PAGE.value: CollectionStrategy.BROWSER.value,
    AtsType.UNKNOWN.value: CollectionStrategy.NONE.value,
}


def build_collector(
    ats_type: str,
    client: httpx.AsyncClient,
    settings: Settings,
) -> JobCollector | None:
    """Return an adapter for this ATS, or None when none is implemented."""
    factory = ADAPTERS.get(ats_type)
    if factory is None:
        return None
    return factory(client, settings)


def supported_ats_types() -> frozenset[str]:
    return frozenset(ADAPTERS)


def strategy_for(ats_type: str) -> str:
    return STRATEGY_BY_ATS.get(ats_type, CollectionStrategy.NONE.value)


def missing_adapter_reason(ats_type: str) -> str:
    return KNOWN_WITHOUT_ADAPTER.get(ats_type, "no adapter registered for this ATS")
