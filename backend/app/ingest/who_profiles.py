from __future__ import annotations

from dataclasses import dataclass


WHO_SURVEILLANCE_MVP_V1 = "who_surveillance_mvp_v1"


@dataclass(frozen=True)
class WhoProfileCode:
    code: str
    category: str


def get_who_surveillance_profile() -> tuple[str, list[WhoProfileCode]]:
    codes = [
        WhoProfileCode("IHR03", "surveillance_capacity"),
        WhoProfileCode("IHR04", "surveillance_capacity"),
        WhoProfileCode("IHR05", "surveillance_capacity"),
        WhoProfileCode("IHR06", "surveillance_capacity"),
        WhoProfileCode("IHR08", "surveillance_capacity"),
        WhoProfileCode("IHR10", "surveillance_capacity"),
        WhoProfileCode("SDGIHR2021", "surveillance_capacity"),
        WhoProfileCode("WHS3_62", "event_signals"),
        WhoProfileCode("WHS3_51", "event_signals"),
        WhoProfileCode("WHS3_47", "event_signals"),
        WhoProfileCode("WHS3_48", "event_signals"),
        WhoProfileCode("WHS3_54", "event_signals"),
        WhoProfileCode("CHOLERA_0000000001", "event_signals"),
        WhoProfileCode("MDG_0000000020", "event_signals"),
        WhoProfileCode("TB_e_inc_num", "event_signals"),
        WhoProfileCode("MALARIA_EST_INCIDENCE", "event_signals"),
        WhoProfileCode("MALARIA_EST_DEATHS", "event_signals"),
        WhoProfileCode("HIV_0000000026", "event_signals"),
        WhoProfileCode("HEPATITIS_HBV_PREVALENCE_PER100", "event_signals"),
        WhoProfileCode("AMRGLASS_SURVL01", "risk_modifiers"),
        WhoProfileCode("AMRGLASS_SURVL02", "risk_modifiers"),
        WhoProfileCode("AMRGLASS_SURVL03", "risk_modifiers"),
        WhoProfileCode("AMRGLASS_COORD01", "risk_modifiers"),
        WhoProfileCode("WHS8_110", "risk_modifiers"),
        WhoProfileCode("MCV2", "risk_modifiers"),
        WhoProfileCode("WHS4_117", "risk_modifiers"),
        WhoProfileCode("WHS4_544", "risk_modifiers"),
        WhoProfileCode("dptv", "risk_modifiers"),
        WhoProfileCode("fullv", "risk_modifiers"),
    ]
    return WHO_SURVEILLANCE_MVP_V1, codes
