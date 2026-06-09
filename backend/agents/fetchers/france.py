from __future__ import annotations

from typing import Any

import httpx

from agents.config import SOURCE_URLS
from agents.normalizers.protected_fields import (
    build_protected_fields,
    first_text,
    split_source_list,
)
from agents.source_types import SourceRecord
from models.pipeline_options import RecallSource


def parse_france_payload(payload: dict[str, Any], *, limit: int) -> list[SourceRecord]:
    records = payload.get("results", [])
    parsed: list[SourceRecord] = []

    for raw_record in records[:limit]:
        if not isinstance(raw_record, dict):
            continue

        try:
            parsed.append(_build_france_record(raw_record))
        except ValueError:
            continue

    return parsed


async def fetch_france_records(
    *,
    limit: int,
    client: httpx.AsyncClient,
) -> list[SourceRecord]:
    response = await client.get(SOURCE_URLS[RecallSource.FRANCE])
    response.raise_for_status()
    return parse_france_payload(response.json(), limit=limit)


def _build_france_record(raw_record: dict[str, Any]) -> SourceRecord:
    protected_fields = build_protected_fields(
        product_name=first_text(
            raw_record.get("libelle"),
            raw_record.get("modeles_ou_references"),
            raw_record.get("marque_produit"),
        ),
        recall_date=raw_record.get("date_publication"),
        source_url=first_text(raw_record.get("lien_vers_la_fiche_rappel")),
    )

    working_json = {
        "source": RecallSource.FRANCE.value,
        "product_details": {
            "brand": first_text(raw_record.get("marque_produit")),
            "model_or_reference": first_text(raw_record.get("modeles_ou_references")),
            "identification": split_source_list(raw_record.get("identification_produits")),
            "packaging": first_text(raw_record.get("conditionnements")),
        },
        "product_category": first_text(
            raw_record.get("sous_categorie_produit"),
            raw_record.get("categorie_produit"),
        ),
        "recall_reason": first_text(raw_record.get("motif_rappel")),
        "risk_details": first_text(
            raw_record.get("risques_encourus"),
            raw_record.get("description_complementaire_risque"),
        ),
        "consumer_action": first_text(
            raw_record.get("conduites_a_tenir_par_le_consommateur")
        ),
        "health_recommendations": first_text(raw_record.get("preconisations_sanitaires")),
        "affected_regions": split_source_list(
            raw_record.get("zone_geographique_de_vente")
        ),
        "distributors": split_source_list(raw_record.get("distributeurs")),
        "recall_end_date": first_text(raw_record.get("date_de_fin_de_la_procedure_de_rappel")),
    }

    return SourceRecord(
        source=RecallSource.FRANCE,
        raw_record=raw_record,
        protected_fields=protected_fields,
        working_json=working_json,
    )
