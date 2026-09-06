"""Verified ATS board tokens for target companies.

These are checked before blind probing. A entry is only used when the live
feed still responds; stale tokens are ignored automatically.
"""

from app.core.enums import AtsType

# slug -> ats_type + board_token (+ optional feed_url)
KNOWN_ATS_BY_SLUG: dict[str, dict[str, str | None]] = {
    "adyen": {"ats_type": AtsType.GREENHOUSE.value, "board_token": "adyen"},
    "binance": {"ats_type": AtsType.LEVER.value, "board_token": "binance"},
    "booking": {"ats_type": AtsType.ICIMS.value, "board_token": "internal-workingatbooking"},
    "careem": {"ats_type": AtsType.GREENHOUSE.value, "board_token": "careem"},
    "careem-saudi": {"ats_type": AtsType.GREENHOUSE.value, "board_token": "careem"},
    "careem-pay": {"ats_type": AtsType.GREENHOUSE.value, "board_token": "careem"},
    "databricks": {"ats_type": AtsType.GREENHOUSE.value, "board_token": "databricks"},
    "delivery-hero": {"ats_type": AtsType.SMARTRECRUITERS.value, "board_token": "Deliveryhero"},
    "dubizzle-group": {"ats_type": AtsType.WORKABLE.value, "board_token": "bayutdubizzle"},
    "elastic": {"ats_type": AtsType.GREENHOUSE.value, "board_token": "elastic"},
    "hubspot": {"ats_type": AtsType.GREENHOUSE.value, "board_token": "hubspotjobs"},
    "hubspot-germany": {"ats_type": AtsType.GREENHOUSE.value, "board_token": "hubspotjobs"},
    "intercom": {"ats_type": AtsType.GREENHOUSE.value, "board_token": "intercom"},
    "kitopi": {"ats_type": AtsType.LEVER.value, "board_token": "kitopi"},
    "miro": {"ats_type": AtsType.ASHBY.value, "board_token": "miro"},
    "n26": {"ats_type": AtsType.GREENHOUSE.value, "board_token": "n26"},
    "personio": {"ats_type": AtsType.PERSONIO_XML.value, "board_token": "personio"},
    "picnic": {"ats_type": AtsType.GREENHOUSE.value, "board_token": "teampicnic"},
    "pipedrive": {"ats_type": AtsType.LEVER.value, "board_token": "pipedrive"},
    "pleo": {"ats_type": AtsType.ASHBY.value, "board_token": "pleo"},
    "tamara": {"ats_type": AtsType.GREENHOUSE.value, "board_token": "tamara"},
    "wolt": {"ats_type": AtsType.WORKABLE.value, "board_token": "wolt"},
}
