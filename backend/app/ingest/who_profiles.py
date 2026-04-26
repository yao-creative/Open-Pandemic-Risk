from __future__ import annotations

from dataclasses import dataclass


WHO_SURVEILLANCE_MVP_V1 = "who_surveillance_mvp_v1"


@dataclass(frozen=True)
class WhoProfileCode:
    code: str
    category: str
    label: str
    risk_direction: str


def get_who_surveillance_profile() -> tuple[str, list[WhoProfileCode]]:
    codes = [
        WhoProfileCode(
            "SDGIHR2021",
            "surveillance_readiness",
            "SPAR core capacity score",
            "higher_is_better",
        ),
        WhoProfileCode(
            "WHS8_110",
            "surveillance_readiness",
            "MCV1 immunization coverage",
            "higher_is_better",
        ),
        WhoProfileCode(
            "MCV2",
            "surveillance_readiness",
            "MCV2 immunization coverage",
            "higher_is_better",
        ),
        WhoProfileCode(
            "WHS4_117",
            "surveillance_readiness",
            "HepB3 immunization coverage",
            "higher_is_better",
        ),
        WhoProfileCode(
            "WHS4_544",
            "surveillance_readiness",
            "Pol3 immunization coverage",
            "higher_is_better",
        ),
        WhoProfileCode(
            "MDG_0000000020",
            "disease_burden",
            "TB incidence per 100,000",
            "higher_is_worse",
        ),
        WhoProfileCode(
            "TB_e_inc_num",
            "disease_burden",
            "Incident tuberculosis cases",
            "higher_is_worse",
        ),
        WhoProfileCode(
            "MALARIA_EST_INCIDENCE",
            "disease_burden",
            "Estimated malaria incidence",
            "higher_is_worse",
        ),
        WhoProfileCode(
            "MALARIA_EST_DEATHS",
            "disease_burden",
            "Estimated malaria deaths",
            "higher_is_worse",
        ),
        WhoProfileCode(
            "HEPATITIS_HBV_PREVALENCE_PER100",
            "disease_burden",
            "Chronic hepatitis B prevalence",
            "higher_is_worse",
        ),
        WhoProfileCode(
            "WHS3_62",
            "disease_burden",
            "Reported measles cases",
            "higher_is_worse",
        ),
    ]
    return WHO_SURVEILLANCE_MVP_V1, codes
