"""Renders the reports for the operations team as Markdown."""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import date, datetime
from typing import TypeVar

from expreso_bridge.upload import Outcome, UploadResult

Row = TypeVar("Row")

ACTION_HEADERS = ["Remito", "Destinatario", "Resultado", "Motivo", "Observaciones"]
DONE_HEADERS = ["Remito", "Destinatario", "Resultado", "Tracking", "Detalle"]
OVERDUE_HEADERS = ["Remito", "Tracking", "Estado", "Entrega estimada"]


def render_run_report(
    results: list[UploadResult],
    *,
    export_name: str,
    export_total: int,
    generated_at: datetime,
) -> str:
    counts = Counter(result.outcome for result in results)
    needs_action = [result for result in results if result.outcome.needs_action]
    no_action = [result for result in results if not result.outcome.needs_action]

    lines = [
        "# Resumen de corrida · Expreso Andino",
        "",
        f"- Export: `{export_name}`",
        f"- Corrida: {generated_at:%Y-%m-%d %H:%M:%S}",
        f"- Remitos en el export: {export_total} · para Expreso Andino: {len(results)}",
        "",
        "| Resultado | Cantidad |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {outcome.value} | {counts[outcome]} |" for outcome in Outcome)

    lines.extend([
        "",
        f"## Requieren acción ({len(needs_action)})",
        "",
        "- **Rechazado**: corregir el dato en el sistema de LogiSur y volver a correr.",
        "- **Falló**: error del lado del expreso; volver a correr (es seguro, no duplica envíos).",
        "",
    ])
    lines.extend(_table(needs_action, ACTION_HEADERS, _action_row))

    lines.extend(["", f"## Sin acción pendiente ({len(no_action)})", ""])
    lines.extend(_table(no_action, DONE_HEADERS, _done_row))
    return "\n".join(lines) + "\n"


def render_overdue_report(shipments: list[dict], *, today: date) -> str:
    lines = [f"# Envíos atrasados al {today:%Y-%m-%d} ({len(shipments)})", ""]
    lines.extend(_table(shipments, OVERDUE_HEADERS, _overdue_row))
    return "\n".join(lines) + "\n"


def _table(items: list[Row], headers: list[str], to_row: Callable[[Row], list[str]]) -> list[str]:
    if not items:
        return ["_Ninguno._"]
    rows = [headers, ["---"] * len(headers)]
    rows.extend(to_row(item) for item in items)
    return ["| " + " | ".join(_cell(value) for value in row) + " |" for row in rows]


def _action_row(result: UploadResult) -> list[str]:
    return [
        result.remito_number,
        result.recipient,
        result.outcome.value,
        result.detail,
        result.observations,
    ]


def _done_row(result: UploadResult) -> list[str]:
    return [
        result.remito_number,
        result.recipient,
        result.outcome.value,
        result.tracking_id,
        result.detail,
    ]


def _overdue_row(shipment: dict) -> list[str]:
    return [
        shipment["external_ref"],
        shipment["tracking_id"],
        shipment["status"],
        shipment["estimated_delivery"],
    ]


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
