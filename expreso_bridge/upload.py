"""Uploads remitos as shipments and classifies what happened to each one."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from expreso_bridge.client import TRANSIENT_STATUSES, ApiResponse, ApiUnavailable, ExpresoClient
from expreso_bridge.remitos import InvalidRemito, build_province_lookup, to_shipment

logger = logging.getLogger(__name__)

# API fields named as they appear in LogiSur's export, which is where operations fixes them.
EXPORT_FIELD_BY_API_FIELD = {
    "external_ref": "nro_remito",
    "recipient.name": "destinatario.razon_social",
    "recipient.street": "destinatario.direccion",
    "recipient.city": "destinatario.localidad",
    "recipient.province": "destinatario.provincia",
    "recipient.zip_code": "destinatario.codigo_postal",
    "packages": "bultos",
    "weight_kg": "peso_kg",
    "declared_value": "valor_declarado",
    "service": "servicio",
}


class Outcome(Enum):
    CREATED = "Cargado"
    ALREADY_EXISTS = "Ya existía"
    DUPLICATE = "Duplicado en el export"
    REJECTED = "Rechazado"
    FAILED = "Falló"

    @property
    def needs_action(self) -> bool:
        return self in (Outcome.REJECTED, Outcome.FAILED)


@dataclass(frozen=True)
class UploadResult:
    remito_number: str
    recipient: str
    outcome: Outcome
    tracking_id: str = ""
    detail: str = ""
    observations: str = ""


def upload_remitos(remitos: list[dict], client: ExpresoClient) -> list[UploadResult]:
    province_lookup = build_province_lookup(client.list_provinces())
    uploaded_numbers = set()
    results = []
    for remito in remitos:
        if remito["nro_remito"] in uploaded_numbers:
            result = _result(remito, Outcome.DUPLICATE, detail="se procesó solo la primera aparición")
        else:
            uploaded_numbers.add(remito["nro_remito"])
            result = _upload_one(remito, province_lookup, client)
        logger.info("%s %s %s %s", result.remito_number, result.outcome.value, result.tracking_id, result.detail)
        results.append(result)
    return results


def _upload_one(remito: dict, province_lookup: dict[str, str], client: ExpresoClient) -> UploadResult:
    try:
        shipment = to_shipment(remito, province_lookup)
    except InvalidRemito as error:
        return _result(remito, Outcome.REJECTED, detail=str(error))
    try:
        response = client.create_shipment(shipment)
    except ApiUnavailable as error:
        return _result(remito, Outcome.FAILED, detail=str(error))
    return _classify(remito, response)


def _classify(remito: dict, response: ApiResponse) -> UploadResult:
    tracking_id = response.body.get("tracking_id", "")
    if response.status == 201:
        return _result(remito, Outcome.CREATED, tracking_id)
    if response.status == 409 and response.attempts > 1:
        # An earlier attempt got a server error but the shipment was stored anyway.
        return _result(
            remito,
            Outcome.CREATED,
            tracking_id,
            detail=f"confirmado en el intento {response.attempts} tras un error de la API",
        )
    if response.status == 409:
        return _result(remito, Outcome.ALREADY_EXISTS, tracking_id)
    if response.status == 422:
        return _result(remito, Outcome.REJECTED, detail=_describe_validation_errors(response.body))
    if response.status in TRANSIENT_STATUSES:
        return _result(
            remito,
            Outcome.FAILED,
            detail=f"la API respondió {response.status} en los {response.attempts} intentos",
        )
    return _result(remito, Outcome.FAILED, detail=f"respuesta inesperada de la API ({response.status}): {response.body}")


def _describe_validation_errors(body: dict) -> str:
    problems = []
    for error in body.get("details", []):
        field = EXPORT_FIELD_BY_API_FIELD.get(error.get("field"), error.get("field"))
        problems.append(f"{field}: {error.get('message')}")
    return "; ".join(problems) or "la API rechazó los datos sin detalle"


def _result(remito: dict, outcome: Outcome, tracking_id: str = "", detail: str = "") -> UploadResult:
    recipient = remito.get("destinatario") or {}
    return UploadResult(
        remito_number=remito["nro_remito"],
        recipient=recipient.get("razon_social", ""),
        outcome=outcome,
        tracking_id=tracking_id,
        detail=detail,
        observations=remito.get("observaciones") or "",
    )
