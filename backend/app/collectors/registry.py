import httpx

from app.collectors.base import JobCollector
from app.collectors.career_page import CareerPageCollector
from app.collectors.greenhouse import GreenhouseCollector
from app.collectors.lever import LeverCollector
from app.collectors.personio import PersonioXmlCollector
from app.core.config import Settings
from app.core.enums import AtsType
from app.models import TargetCompany


def collector_for(
    company: TargetCompany,
    client: httpx.AsyncClient,
    settings: Settings,
) -> JobCollector:
    mapping: dict[str, JobCollector] = {
        AtsType.GREENHOUSE.value: GreenhouseCollector(client, settings),
        AtsType.LEVER.value: LeverCollector(client, settings),
        AtsType.PERSONIO_XML.value: PersonioXmlCollector(client, settings),
        AtsType.CAREER_PAGE.value: CareerPageCollector(),
    }
    return mapping.get(company.ats_type, CareerPageCollector())
