"""Composición por registro: diagnóstico + compensación + ROI en un solo resultado.

No hace IO ni formatea: solo encadena las funciones puras de cada módulo.
"""

from __future__ import annotations

from dataclasses import dataclass

from power_factor.compensation import (
    BankSuggestion,
    capacitance_per_phase_uf,
    required_kvar,
    suggest_commercial_size,
)
from power_factor.config import Settings
from power_factor.diagnose import (
    EconomicImpact,
    EstadoFP,
    classify_fp,
    diagnostic_comment,
    economic_impact,
)
from power_factor.roi import monthly_savings_mxn, simple_roi_months, template_savings_mxn
from power_factor.schemas import BillingRecord


@dataclass(frozen=True)
class RecordAnalysis:
    record: BillingRecord
    estado: EstadoFP
    comentario: str
    impacto: EconomicImpact
    fp_objetivo: float
    q_requerida_kvar: float
    capacitancia_uf: float
    banco: BankSuggestion
    ahorro_mensual_mxn: float
    roi_meses: float | None
    ahorro_plantilla_mxn: float

    @property
    def diferencia_vs_plantilla_mxn(self) -> float:
        return self.ahorro_mensual_mxn - self.ahorro_plantilla_mxn


@dataclass(frozen=True)
class ExcludedRecord:
    """Registro con id_registro que no pasó la limpieza: se reporta, no se calcula."""

    id_registro: str
    cliente: str | None
    fila_excel: int
    motivos: tuple[str, ...]


def analyze_record(record: BillingRecord, settings: Settings) -> RecordAnalysis:
    fp = record.fp_actual
    estado = classify_fp(fp, settings.fp_objetivo, settings.cfe.umbral_fp)
    impacto = economic_impact(fp, record.subtotal, settings.cfe)

    qc = required_kvar(record.demanda_max_kw, fp, settings.fp_objetivo)
    capacitancia = capacitance_per_phase_uf(
        qc, settings.voltaje_v, settings.frecuencia_hz, settings.conexion
    )
    banco = suggest_commercial_size(qc, settings.tamanos_comerciales_kvar)

    comentario = diagnostic_comment(estado, fp, settings.fp_objetivo, impacto.ajuste_pct)
    if banco.excede_serie:
        comentario += (f" Qc={qc:.1f} kVAr excede la serie comercial: se sugiere "
                       f"{banco.describe()}, validar con ingeniería.")

    ahorro = monthly_savings_mxn(fp, record.subtotal, settings.fp_objetivo, settings.cfe)
    return RecordAnalysis(
        record=record,
        estado=estado,
        comentario=comentario,
        impacto=impacto,
        fp_objetivo=settings.fp_objetivo,
        q_requerida_kvar=qc,
        capacitancia_uf=capacitancia,
        banco=banco,
        ahorro_mensual_mxn=ahorro,
        roi_meses=simple_roi_months(record.costo_banco_capturado_mxn, ahorro),
        ahorro_plantilla_mxn=template_savings_mxn(fp, record.subtotal, settings.cfe.umbral_fp),
    )
