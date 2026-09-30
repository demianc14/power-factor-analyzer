"""Orquestador Extract -> Transform -> Load. La CLI solo parsea argumentos y llama aquí."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from power_factor.analysis import ExcludedRecord, RecordAnalysis, analyze_record
from power_factor.clean import DataQualityReport, clean_billing, is_missing
from power_factor.config import Settings
from power_factor.extract import read_billing_sheet
from power_factor.plot import plot_fp_trend
from power_factor.report import build_sheets, write_workbook

PLOT_FILENAME = "tendencia_fp.png"
QUALITY_CSV_FILENAME = "calidad_datos.csv"


@dataclass(frozen=True)
class PipelineResult:
    analyses: tuple[RecordAnalysis, ...]
    excluded: tuple[ExcludedRecord, ...]
    report: DataQualityReport
    sheets: dict[str, pd.DataFrame]
    output_xlsx: Path
    quality_csv: Path
    plot_png: Path | None


def excluded_records(raw: pd.DataFrame, report: DataQualityReport,
                     valid_ids: set[str]) -> tuple[ExcludedRecord, ...]:
    """Filas con id_registro que no llegaron al cálculo (para que no desaparezcan de 02/03)."""
    first_row: dict[str, int] = {}
    for issue in report.issues:
        if issue.id_registro and issue.id_registro not in first_row:
            first_row[issue.id_registro] = issue.fila_excel
    salida = []
    for id_registro, motivos in report.motivos_exclusion().items():
        if id_registro in valid_ids:  # p. ej. la copia descartada de un duplicado exacto
            continue
        fila = first_row[id_registro]
        cliente_raw = raw.iloc[fila - 2]["cliente"]
        cliente = None if is_missing(cliente_raw) else str(cliente_raw).strip()
        salida.append(ExcludedRecord(id_registro, cliente, fila, tuple(dict.fromkeys(motivos))))
    return tuple(salida)


def run_pipeline(
    input_path: str | Path,
    output_xlsx: str | Path,
    settings: Settings | None = None,
    *,
    fecha: date | None = None,
    sheet: str | None = None,
    plot: bool = True,
) -> PipelineResult:
    settings = settings or Settings()
    fecha = fecha or date.today()
    output_xlsx = Path(output_xlsx)

    raw = read_billing_sheet(input_path, sheet=sheet)                        # Extract
    limpio = clean_billing(raw, settings)                                    # Transform
    analyses = tuple(analyze_record(r, settings) for r in limpio.records)
    excluded = excluded_records(raw, limpio.report,
                                {r.id_registro for r in limpio.records})

    sheets = build_sheets(raw, analyses, excluded, limpio.report, settings, fecha)  # Load
    write_workbook(output_xlsx, sheets)
    quality_csv = output_xlsx.parent / QUALITY_CSV_FILENAME
    limpio.report.to_frame().to_csv(quality_csv, index=False, encoding="utf-8-sig")
    plot_png = None
    if plot and analyses:
        plot_png = plot_fp_trend(analyses, settings.fp_objetivo,
                                 output_xlsx.parent / PLOT_FILENAME, settings.cfe.umbral_fp)
    return PipelineResult(analyses, excluded, limpio.report, sheets, output_xlsx,
                          quality_csv, plot_png)
