"""Transform (2/2): estado del FP e impacto económico según la fórmula CFE.

Convención de signo del *ajuste CFE*: positivo = cargo (penalización),
negativo = bonificación. `impacto_neto_mxn` de la Hoja 2 sigue el contrato
COIL (bonificación - penalización), es decir, el signo contrario.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from power_factor.config import CfeTariffParams

# Tolerancia para comparar el FP contra fronteras (0.90 y fp_objetivo) en punto flotante.
FP_ABS_TOL = 1e-9


class EstadoFP(StrEnum):
    PENALIZACION = "Penalización"
    NEUTRO = "Neutro"
    BONIFICACION = "Bonificación"
    META_CUMPLIDA = "Meta cumplida"


@dataclass(frozen=True)
class EconomicImpact:
    ajuste_pct: float
    penalizacion_mxn: float
    bonificacion_mxn: float

    @property
    def impacto_neto_mxn(self) -> float:
        return self.bonificacion_mxn - self.penalizacion_mxn


def _validate_fp(fp: float) -> None:
    if not 0 < fp <= 1:
        raise ValueError(f"FP fuera de (0, 1]: {fp}")


def classify_fp(fp: float, fp_objetivo: float, umbral: float = 0.90) -> EstadoFP:
    """'Meta cumplida' tiene precedencia sobre 'Bonificación' cuando FP >= objetivo."""
    _validate_fp(fp)
    if fp > fp_objetivo or math.isclose(fp, fp_objetivo, abs_tol=FP_ABS_TOL):
        return EstadoFP.META_CUMPLIDA
    if math.isclose(fp, umbral, abs_tol=FP_ABS_TOL):
        return EstadoFP.NEUTRO
    return EstadoFP.PENALIZACION if fp < umbral else EstadoFP.BONIFICACION


def cfe_adjustment_pct(fp: float, params: CfeTariffParams) -> float:
    """Ajuste por FP en % del subtotal (positivo = cargo, negativo = bonificación).

    TODO verificar contra tarifa vigente.
    - FP < 0.90: cargo  = 3/5 · (0.90/FP - 1) · 100, tope 120 %.
    - FP > 0.90: bonif. = 1/4 · (1 - 0.90/FP) · 100, tope 2.5 %.
    """
    _validate_fp(fp)
    u = params.umbral_fp
    if math.isclose(fp, u, abs_tol=FP_ABS_TOL):
        return 0.0
    if fp < u:
        return min(params.factor_penalizacion * (u / fp - 1) * 100, params.tope_penalizacion_pct)
    return -min(params.factor_bonificacion * (1 - u / fp) * 100, params.tope_bonificacion_pct)


def cfe_adjustment_mxn(fp: float, base_mxn: float, params: CfeTariffParams) -> float:
    """Ajuste en MXN sobre la base de cálculo (SUPUESTO: base = columna `subtotal`)."""
    if base_mxn < 0:
        raise ValueError(f"La base del ajuste no puede ser negativa: {base_mxn}")
    return cfe_adjustment_pct(fp, params) / 100 * base_mxn


def economic_impact(fp: float, subtotal: float, params: CfeTariffParams) -> EconomicImpact:
    pct = cfe_adjustment_pct(fp, params)
    monto = cfe_adjustment_mxn(fp, subtotal, params)
    return EconomicImpact(
        ajuste_pct=pct,
        penalizacion_mxn=max(0.0, monto),
        bonificacion_mxn=max(0.0, -monto),  # max(0.0, -0.0) -> 0.0, sin "-0"
    )


def diagnostic_comment(estado: EstadoFP, fp: float, fp_objetivo: float, ajuste_pct: float) -> str:
    if estado is EstadoFP.PENALIZACION:
        return (f"FP {fp:.3f} < 0.90: cargo estimado de {ajuste_pct:.2f} % del subtotal. "
                f"Requiere compensación reactiva hasta {fp_objetivo:.2f}.")
    if estado is EstadoFP.NEUTRO:
        return (f"FP {fp:.3f} = 0.90: sin cargo ni bonificación. "
                f"Compensar hasta {fp_objetivo:.2f} daría bonificación.")
    if estado is EstadoFP.BONIFICACION:
        return (f"FP {fp:.3f} > 0.90: bonificación estimada de {-ajuste_pct:.2f} % del subtotal, "
                f"aún debajo de la meta {fp_objetivo:.2f}.")
    return f"FP {fp:.3f} cumple la meta {fp_objetivo:.2f}: no requiere compensación."
