"""Reads LogiSur's daily export and maps each remito to an Expreso Andino shipment."""
from __future__ import annotations

import json
import math
import unicodedata
from pathlib import Path

ANDINO_CARRIER_NAMES = {"expreso andino", "exp. andino"}

SERVICE_BY_REMITO_SERVICE = {"normal": "standard", "urgente": "express"}

# Abbreviations seen in the export. Spelling variants without accents
# ("Tucuman", "Neuquen") are resolved by normalization, not listed here.
PROVINCE_ALIASES = {
    "ba": "Buenos Aires",
    "bs. as.": "Buenos Aires",
    "cba": "Córdoba",
    "caba": "Ciudad Autónoma de Buenos Aires",
    "capital federal": "Ciudad Autónoma de Buenos Aires",
}

# Inverse of to_shipment, so API errors name the field operations fixes in the export.
EXPORT_FIELD_BY_API_FIELD = {
    "external_ref": "nro_remito",
    "recipient.name": "destinatario.razon_social",
    "recipient.street": "destinatario.direccion",
    "recipient.city": "destinatario.localidad",
    "recipient.province": "destinatario.provincia",
    "recipient.zip_code": "destinatario.codigo_postal",
    "recipient.phone": "destinatario.telefono",
    "packages": "bultos",
    "weight_kg": "peso_kg",
    "declared_value": "valor_declarado",
    "service": "servicio",
}


class InvalidRemito(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def load_remitos(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as export_file:
        return json.load(export_file)


def normalize(text: str) -> str:
    """Case-, accent- and whitespace-insensitive key: ' Neuquén ' -> 'neuquen'."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_accents.casefold().split())


def is_andino(remito: dict) -> bool:
    return normalize(remito.get("transportista") or "") in ANDINO_CARRIER_NAMES


def build_province_lookup(official_names: list[str]) -> dict[str, str]:
    lookup = {normalize(name): name for name in official_names}
    lookup.update(PROVINCE_ALIASES)
    return lookup


def to_shipment(remito: dict, province_lookup: dict[str, str]) -> dict:
    """Maps a remito to the API payload. Raises InvalidRemito when a field cannot be mapped.

    Only mapping problems are checked here; business rules (packages >= 1,
    non-empty address...) stay with the API, which is their source of truth.
    """
    recipient = remito.get("destinatario") or {}
    problems = []

    raw_province = recipient.get("provincia") or ""
    province = province_lookup.get(normalize(raw_province))
    if province is None:
        problems.append(f"provincia desconocida: '{raw_province}'")

    weight_kg = parse_decimal(remito.get("peso_kg"))
    if weight_kg is None:
        problems.append(f"peso inválido: '{remito.get('peso_kg')}'")

    raw_service = remito.get("servicio") or ""
    service = SERVICE_BY_REMITO_SERVICE.get(normalize(raw_service))
    if service is None:
        problems.append(f"servicio desconocido: '{raw_service}'")

    if problems:
        raise InvalidRemito(problems)

    shipment = {
        "external_ref": remito["nro_remito"],
        "recipient": {
            "name": _clean(recipient.get("razon_social")),
            "street": _clean(recipient.get("direccion")),
            "city": _clean(recipient.get("localidad")),
            "province": province,
            "zip_code": _clean(recipient.get("codigo_postal")),
        },
        "packages": remito.get("bultos"),
        "weight_kg": weight_kg,
        "service": service,
    }
    phone = _clean(recipient.get("telefono"))
    if phone:
        shipment["recipient"]["phone"] = phone
    if remito.get("valor_declarado") is not None:
        shipment["declared_value"] = remito["valor_declarado"]
    return shipment


def parse_decimal(value: object) -> float | None:
    """Accepts numbers and strings with a decimal comma ('145,1').

    Strings with thousands separators ('1.234,5') are rejected rather than guessed.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip().replace(",", "."))
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _clean(value: str | None) -> str:
    return (value or "").strip()
