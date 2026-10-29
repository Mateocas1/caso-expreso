"""Finds shipments that are not delivered and whose estimated delivery date has passed."""
from __future__ import annotations

from datetime import date

from expreso_bridge.client import ExpresoClient


def find_overdue(external_refs: list[str], client: ExpresoClient, today: date) -> list[dict]:
    overdue = []
    for external_ref in dict.fromkeys(external_refs):
        for match in client.find_shipments(external_ref):
            shipment = client.get_shipment(match["tracking_id"])
            if is_overdue(shipment, today):
                overdue.append(shipment)
    return overdue


def is_overdue(shipment: dict, today: date) -> bool:
    estimated_delivery = date.fromisoformat(shipment["estimated_delivery"])
    return shipment["status"] != "DELIVERED" and estimated_delivery < today
