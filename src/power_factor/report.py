"""Load: construye las hojas de salida y escribe el xlsx.

Las hojas 02 y 03 respetan exactamente las columnas del contrato COIL (se
validan con los modelos Pydantic). Todo lo adicional (comparación contra la
plantilla, calidad de datos, supuestos) va en hojas aparte para no romper el
contrato.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd

from power_factor.analysis import ExcludedRecord, RecordAnalysis
from power_factor.clean import DataQualityReport
from power_factor.config import Settings
from power_factor.diagnose import EstadoFP
from power_factor.schemas import SHEET2_COLUMNS, SHEET3_COLUMNS, Sheet2Row, Sheet3Row

SHEET1 = "01_Datos_Facturacion"
SHEET2 = "02_Analisis_Economico_Tecnico"
SHEET3 = "03_Resultados_Negocio"
SHEET_COMPARACION = "04_Comparacion_Plantilla"
SHEET_CALIDAD_RESUMEN = "05_Calidad_Resumen"
SHEET_CALIDAD_DETALLE = "06_Calidad_Detalle"
SHEET_SUPUESTOS = "07_Supuestos"

SIN_DIAGNOSTICO = "Sin diagnóstico"

# Redondeo del contrato COIL: dinero 2, FP 3; kVAr 2 y µF 4 por criterio propio.
MONEY_DP, FP_DP, KVAR_DP, UF_DP, MONTHS_DP = 2, 3, 2, 4, 2


def _r(value: float | None, ndigits: int) -> float | None:
    return None if value is None else round(value, ndigits)


def _mxn(value: float) -> str:
    return f"{value:,.2f} MXN"


def build_resumen(a: RecordAnalysis) -> str:
    """Resumen ejecutivo de 2-3 frases: estado, impacto y recomendación."""
    r = a.record
    frase_estado = f"{r.cliente}, periodo {r.periodo}: FP {r.fp_actual:.3f} ({a.estado.value})"
    if a.impacto.penalizacion_mxn > 0:
        impacto = f"cargo estimado de {_mxn(a.impacto.penalizacion_mxn)}/mes"
    elif a.impacto.bonificacion_mxn > 0:
        impacto = f"bonificación estimada de {_mxn(a.impacto.bonificacion_mxn)}/mes"
    else:
        impacto = "sin cargo ni bonificación"
    frases = [f"{frase_estado}, {impacto}."]

    if a.q_requerida_kvar == 0:
        frases.append("No requiere compensación reactiva; mantener monitoreo mensual.")
        return " ".join(frases)

    recomendacion = (f"Se recomienda un banco de {a.banco.describe()} "
                     f"(Qc requerido {a.q_requerida_kvar:.1f} kVAr) para llegar a FP "
                     f"{a.fp_objetivo:.2f}")
    if a.roi_meses is not None:
        recomendacion += (f"; ahorro estimado de {_mxn(a.ahorro_mensual_mxn)}/mes y "
                          f"recuperación en {a.roi_meses:.1f} meses.")
    elif r.costo_banco_capturado_mxn is None:
        recomendacion += "; ROI no calculable: falta el costo del banco."
    else:
        recomendacion += "; ROI no calculable: no hay ahorro estimable."
    frases.append(recomendacion)
    if a.banco.excede_serie:
        frases.append("El Qc excede la serie comercial: validar con ingeniería.")
    return " ".join(frases)


def _excluded_comment(e: ExcludedRecord) -> str:
    return "Excluido por calidad de datos: " + "; ".join(e.motivos)


def _ordered(
    analyses: Sequence[RecordAnalysis], excluded: Sequence[ExcludedRecord]
) -> list[RecordAnalysis | ExcludedRecord]:
    def fila(x: RecordAnalysis | ExcludedRecord) -> int:
        return x.record.fila_excel if isinstance(x, RecordAnalysis) else x.fila_excel

    return sorted([*analyses, *excluded], key=fila)


def build_sheet2(
    analyses: Sequence[RecordAnalysis],
    excluded: Sequence[ExcludedRecord],
    settings: Settings,
) -> pd.DataFrame:
    filas: list[Sheet2Row] = []
    for x in _ordered(analyses, excluded):
        if isinstance(x, ExcludedRecord):
            filas.append(Sheet2Row(
                id_registro=x.id_registro, estado_fp=SIN_DIAGNOSTICO,
                comentario_diagnostico=_excluded_comment(x),
                penalizacion_mxn=None, bonificacion_mxn=None, impacto_neto_mxn=None,
                fp_objetivo=settings.fp_objetivo, q_requerida_kvar=None, capacitancia_uf=None,
                tamano_comercial_sugerido_kvar=None, ahorro_mensual_estimado_mxn=None,
                roi_meses=None,
            ))
            continue
        filas.append(Sheet2Row(
            id_registro=x.record.id_registro,
            estado_fp=x.estado.value,
            comentario_diagnostico=x.comentario,
            penalizacion_mxn=round(x.impacto.penalizacion_mxn, MONEY_DP),
            bonificacion_mxn=round(x.impacto.bonificacion_mxn, MONEY_DP),
            impacto_neto_mxn=round(x.impacto.impacto_neto_mxn, MONEY_DP),
            fp_objetivo=x.fp_objetivo,
            q_requerida_kvar=round(x.q_requerida_kvar, KVAR_DP),
            capacitancia_uf=round(x.capacitancia_uf, UF_DP),
            tamano_comercial_sugerido_kvar=x.banco.total_kvar,
            ahorro_mensual_estimado_mxn=round(x.ahorro_mensual_mxn, MONEY_DP),
            roi_meses=_r(x.roi_meses, MONTHS_DP),
        ))
    return pd.DataFrame([f.model_dump() for f in filas], columns=list(SHEET2_COLUMNS))


def build_sheet3(
    analyses: Sequence[RecordAnalysis],
    excluded: Sequence[ExcludedRecord],
    fecha: date,
) -> pd.DataFrame:
    filas: list[Sheet3Row] = []
    for x in _ordered(analyses, excluded):
        if isinstance(x, ExcludedRecord):
            filas.append(Sheet3Row(
                id_registro=x.id_registro, cliente=x.cliente or "dato no disponible",
                fp_actual=None, estado_fp=SIN_DIAGNOSTICO, impacto_neto_mxn=None,
                tamano_comercial_sugerido_kvar=None, roi_meses=None,
                resumen_reporte=(f"Registro excluido del cálculo ({'; '.join(x.motivos)}). "
                                 f"Ver hoja {SHEET_CALIDAD_DETALLE}."),
                fecha_ultima_actualizacion=fecha,
            ))
            continue
        filas.append(Sheet3Row(
            id_registro=x.record.id_registro,
            cliente=x.record.cliente,
            fp_actual=round(x.record.fp_actual, FP_DP),
            estado_fp=x.estado.value,
            impacto_neto_mxn=round(x.impacto.impacto_neto_mxn, MONEY_DP),
            tamano_comercial_sugerido_kvar=x.banco.total_kvar,
            roi_meses=_r(x.roi_meses, MONTHS_DP),
            resumen_reporte=build_resumen(x),
            fecha_ultima_actualizacion=fecha,
        ))
    return pd.DataFrame([f.model_dump() for f in filas], columns=list(SHEET3_COLUMNS))


def build_comparison_sheet(analyses: Sequence[RecordAnalysis]) -> pd.DataFrame:
    """Nuestro ahorro vs la fórmula simplificada de la plantilla, fila por fila."""
    filas = []
    for a in analyses:
        costo = a.record.costo_banco_capturado_mxn
        roi_plantilla = (costo / a.ahorro_plantilla_mxn
                         if costo is not None and a.ahorro_plantilla_mxn > 0 else None)
        if a.estado in (EstadoFP.BONIFICACION, EstadoFP.META_CUMPLIDA):
            nota = ("La plantilla cuenta como ahorro la bonificación que ya se recibe; "
                    "aquí solo cuenta el incremento hasta el objetivo.")
        elif a.estado is EstadoFP.NEUTRO:
            nota = ("La plantilla da 0 con FP = 0.90; aquí cuenta la bonificación "
                    "alcanzable al compensar hasta el objetivo.")
        else:
            nota = ("La plantilla escala linealmente |FP-0.90|/0.90; aquí se usa la fórmula "
                    "CFE (cargo evitado + bonificación al objetivo).")
        filas.append({
            "id_registro": a.record.id_registro,
            "fp_actual": round(a.record.fp_actual, FP_DP),
            "estado_fp": a.estado.value,
            "ahorro_mensual_estimado_mxn": round(a.ahorro_mensual_mxn, MONEY_DP),
            "ahorro_plantilla": round(a.ahorro_plantilla_mxn, MONEY_DP),
            "diferencia_vs_plantilla": round(a.diferencia_vs_plantilla_mxn, MONEY_DP),
            "roi_meses": _r(a.roi_meses, MONTHS_DP),
            "roi_plantilla_meses": _r(roi_plantilla, MONTHS_DP),
            "nota": nota,
        })
    return pd.DataFrame(filas)


def build_assumptions_sheet(settings: Settings) -> pd.DataFrame:
    notas = {
        "fp_objetivo": "Meta de compensación (el documento COIL usa 0.90; aquí 0.95).",
        "voltaje_v": "SUPUESTO: no viene en el recibo.",
        "frecuencia_hz": "SUPUESTO: red nacional 60 Hz.",
        "conexion": "SUPUESTO: conexión del banco de capacitores.",
        "tamanos_comerciales_kvar": "SUPUESTO: serie didáctica del proyecto COIL.",
        "negative_kw_policy": "reject = se excluye la fila; abs = se toma valor absoluto.",
        "tolerancia_consistencia_fp": "Aviso si |fp_actual - FP(kWh,kVArh)| la supera.",
    }
    filas = [
        {"parametro": k, "valor": str(v), "nota": notas.get(k, "")}
        for k, v in asdict(settings).items() if k != "cfe"
    ]
    filas += [
        {"parametro": f"cfe.{k}", "valor": str(v),
         "nota": "TODO verificar contra tarifa vigente."}
        for k, v in asdict(settings.cfe).items()
    ]
    filas.append({"parametro": "base_ajuste_cfe", "valor": "subtotal",
                  "nota": "SUPUESTO: base de cálculo del cargo/bonificación."})
    return pd.DataFrame(filas)


def build_sheets(
    raw_input: pd.DataFrame,
    analyses: Sequence[RecordAnalysis],
    excluded: Sequence[ExcludedRecord],
    report: DataQualityReport,
    settings: Settings,
    fecha: date,
) -> dict[str, pd.DataFrame]:
    return {
        SHEET1: raw_input,
        SHEET2: build_sheet2(analyses, excluded, settings),
        SHEET3: build_sheet3(analyses, excluded, fecha),
        SHEET_COMPARACION: build_comparison_sheet(analyses),
        SHEET_CALIDAD_RESUMEN: report.summary_frame(),
        SHEET_CALIDAD_DETALLE: report.to_frame(),
        SHEET_SUPUESTOS: build_assumptions_sheet(settings),
    }


def write_workbook(path: str | Path, sheets: Mapping[str, pd.DataFrame]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for nombre, df in sheets.items():
            df.to_excel(writer, sheet_name=nombre, index=False)
            hoja = writer.sheets[nombre]
            for idx, col in enumerate(df.columns, start=1):
                largo = max([len(str(col)), *(len(str(v)) for v in df[col].head(50))])
                hoja.column_dimensions[hoja.cell(row=1, column=idx).column_letter].width = min(
                    largo + 2, 80
                )
    return path
