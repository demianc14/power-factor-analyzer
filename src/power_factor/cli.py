"""CLI del pipeline.

    python -m power_factor.cli run --input <entrada.xlsx> --output <salida.xlsx>

Solo parsea argumentos, arma `Settings` y llama a `run_pipeline`. Los errores de
contrato (columna faltante, archivo inexistente, parámetro inválido) salen con
código 2 y un mensaje claro, sin traceback.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from typing import Any

import pandas as pd

from power_factor.config import CONEXIONES, NEGATIVE_KW_POLICIES, PRESETS, Settings
from power_factor.pipeline import PipelineResult, run_pipeline
from power_factor.report import SHEET3

EXIT_OK = 0
EXIT_INPUT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="power_factor",
        description="Diagnóstico de factor de potencia, compensación reactiva y ROI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Corre Extract -> Transform -> Load sobre un xlsx.")
    run.add_argument("--input", required=True, help="xlsx con la hoja de facturación.")
    run.add_argument("--output", default="output/analisis.xlsx", help="xlsx de salida.")
    run.add_argument("--sheet", default=None, help="Hoja de entrada (default: 'Hoja 1').")
    run.add_argument("--preset", choices=sorted(PRESETS), default="13200_estrella",
                     help="Escenario eléctrico base.")
    run.add_argument("--fp-objetivo", type=float, default=None)
    run.add_argument("--voltaje", type=float, default=None, help="Voltaje de línea en V.")
    run.add_argument("--frecuencia", type=float, default=None, help="Hz.")
    run.add_argument("--conexion", choices=CONEXIONES, default=None)
    run.add_argument("--negative-kw-policy", choices=NEGATIVE_KW_POLICIES, default=None)
    run.add_argument("--fecha", type=date.fromisoformat, default=None,
                     help="fecha_ultima_actualizacion (YYYY-MM-DD); default: hoy.")
    run.add_argument("--no-plot", action="store_true", help="No generar la gráfica.")
    return parser


def settings_from_args(args: argparse.Namespace) -> Settings:
    overrides: dict[str, Any] = {
        "fp_objetivo": args.fp_objetivo,
        "voltaje_v": args.voltaje,
        "frecuencia_hz": args.frecuencia,
        "conexion": args.conexion,
        "negative_kw_policy": args.negative_kw_policy,
    }
    # `replace` vuelve a correr __post_init__: los overrides también se validan.
    return replace(PRESETS[args.preset], **{k: v for k, v in overrides.items() if v is not None})


def render_summary(result: PipelineResult) -> str:
    report = result.report
    lineas = [
        "== Reporte de calidad de datos ==",
        report.summary_frame().to_string(index=False),
    ]
    if report.issues:
        detalle = report.to_frame()[["fila_excel", "id_registro", "tipo", "severidad",
                                     "valor_original"]]
        lineas += ["", detalle.to_string(index=False)]
    resumen = result.sheets[SHEET3][["id_registro", "estado_fp", "impacto_neto_mxn",
                                     "tamano_comercial_sugerido_kvar", "roi_meses"]]
    with pd.option_context("display.width", 120):
        lineas += ["", "== Resultados (03_Resultados_Negocio) ==", resumen.to_string(index=False)]
    lineas += ["", f"xlsx:    {result.output_xlsx}", f"calidad: {result.quality_csv}"]
    if result.plot_png is not None:
        lineas.append(f"gráfica: {result.plot_png}")
    return "\n".join(lineas)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = settings_from_args(args)
        result = run_pipeline(args.input, args.output, settings, fecha=args.fecha,
                              sheet=args.sheet, plot=not args.no_plot)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    print(render_summary(result))
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover  (cubierto por test_module_entrypoint)
    sys.exit(main())
