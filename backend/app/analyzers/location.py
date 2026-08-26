import re
from dataclasses import dataclass

COUNTRY_NAMES: dict[str, str] = {
    "united arab emirates": "AE",
    "uae": "AE",
    "dubai": "AE",
    "abu dhabi": "AE",
    "germany": "DE",
    "deutschland": "DE",
    "berlin": "DE",
    "munich": "DE",
    "münchen": "DE",
    "hamburg": "DE",
    "netherlands": "NL",
    "the netherlands": "NL",
    "holland": "NL",
    "amsterdam": "NL",
    "ireland": "IE",
    "dublin": "IE",
    "saudi arabia": "SA",
    "riyadh": "SA",
    "estonia": "EE",
    "tallinn": "EE",
    "portugal": "PT",
    "lisbon": "PT",
    "lisboa": "PT",
    "sweden": "SE",
    "sverige": "SE",
    "stockholm": "SE",
    "gothenburg": "SE",
    "göteborg": "SE",
    "malmö": "SE",
    "denmark": "DK",
    "danmark": "DK",
    "copenhagen": "DK",
    "københavn": "DK",
    "aarhus": "DK",
    "finland": "FI",
    "suomi": "FI",
    "helsinki": "FI",
    "espoo": "FI",
    "norway": "NO",
    "norge": "NO",
    "oslo": "NO",
    "bergen": "NO",
    "fornebu": "NO",
    "canada": "CA",
    "toronto": "CA",
    "vancouver": "CA",
    "spain": "ES",
    "barcelona": "ES",
    "madrid": "ES",
    "united kingdom": "GB",
    "uk": "GB",
    "london": "GB",
    "united states": "US",
    "usa": "US",
    "us": "US",
    "new york": "US",
    "san francisco": "US",
    "india": "IN",
    "bangalore": "IN",
    "bengaluru": "IN",
    "france": "FR",
    "paris": "FR",
}

CITY_TO_COUNTRY = {
    "dubai": "AE",
    "berlin": "DE",
    "munich": "DE",
    "amsterdam": "NL",
    "dublin": "IE",
    "tallinn": "EE",
    "lisbon": "PT",
    "riyadh": "SA",
    "jeddah": "SA",
    "neom": "SA",
    "dhahran": "SA",
    "stockholm": "SE",
    "gothenburg": "SE",
    "copenhagen": "DK",
    "helsinki": "FI",
    "espoo": "FI",
    "oslo": "NO",
    "utrecht": "NL",
    "abu dhabi": "AE",
    "barcelona": "ES",
    "london": "GB",
}


@dataclass(frozen=True)
class ParsedLocation:
    raw: str
    country: str | None
    city: str | None
    remote_hint: bool


def parse_location(value: str | None) -> ParsedLocation:
    raw = (value or "").strip()
    lowered = raw.lower()
    remote_hint = any(token in lowered for token in ("remote", "work from home", "wfh"))
    if not raw:
        return ParsedLocation(raw="", country=None, city=None, remote_hint=remote_hint)

    country = None
    city = None
    for name, code in COUNTRY_NAMES.items():
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            country = code
            break
    for name, code in CITY_TO_COUNTRY.items():
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            city = name.title()
            country = country or code
            break

    parts = [part.strip() for part in re.split(r"[,/|]", raw) if part.strip()]
    if parts and city is None:
        city = parts[0]
    return ParsedLocation(raw=raw, country=country, city=city, remote_hint=remote_hint)
