"""Command line entry point: python -m expreso_bridge {upload,overdue} <export.json>."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

from expreso_bridge.client import ApiError, ExpresoClient
from expreso_bridge.remitos import is_andino, load_remitos
from expreso_bridge.overdue import find_overdue
from expreso_bridge.report import render_overdue_report, render_run_report
from expreso_bridge.upload import upload_remitos

DEFAULT_API_URL = "http://localhost:8000"

EXIT_OK = 0
EXIT_NEEDS_ACTION = 1
EXIT_CANNOT_RUN = 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    api_key = os.environ.get("EXPRESO_API_KEY")
    if not api_key:
        print("Falta la variable de entorno EXPRESO_API_KEY.", file=sys.stderr)
        return EXIT_CANNOT_RUN
    client = ExpresoClient(os.environ.get("EXPRESO_API_URL", DEFAULT_API_URL), api_key)

    try:
        if args.command == "overdue":
            return _overdue(args.export, args.today, client)
        return _upload(args.export, args.reports_dir, client)
    except ApiError as error:
        print(f"No se pudo completar la corrida: {error}", file=sys.stderr)
        return EXIT_CANNOT_RUN


def _upload(export_path: Path, reports_dir: Path, client: ExpresoClient) -> int:
    remitos = load_remitos(export_path)
    andino_remitos = [remito for remito in remitos if is_andino(remito)]
    results = upload_remitos(andino_remitos, client)

    generated_at = datetime.now()
    report = render_run_report(
        results,
        export_name=export_path.name,
        export_total=len(remitos),
        generated_at=generated_at,
    )
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"corrida_{generated_at:%Y-%m-%dT%H%M%S_%f}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Resumen escrito en {report_path}")

    needs_action = any(result.outcome.needs_action for result in results)
    return EXIT_NEEDS_ACTION if needs_action else EXIT_OK


def _overdue(export_path: Path, today: date, client: ExpresoClient) -> int:
    external_refs = [remito["nro_remito"] for remito in load_remitos(export_path) if is_andino(remito)]
    print(render_overdue_report(find_overdue(external_refs, client, today), today=today), end="")
    return EXIT_OK


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m expreso_bridge",
        description="Carga en la API de Expreso Andino los remitos del export diario de LogiSur.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    upload = commands.add_parser("upload", help="cargar los remitos de Expreso Andino de un export")
    upload.add_argument("export", type=Path, help="archivo JSON exportado por LogiSur")
    upload.add_argument("--reports-dir", type=Path, default=Path("reports"), help="carpeta del resumen (default: reports)")

    overdue = commands.add_parser("overdue", help="listar envíos no entregados con fecha estimada vencida")
    overdue.add_argument("export", type=Path, help="archivo JSON exportado por LogiSur")
    overdue.add_argument("--today", type=date.fromisoformat, default=date.today(), help="fecha de referencia (YYYY-MM-DD)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
