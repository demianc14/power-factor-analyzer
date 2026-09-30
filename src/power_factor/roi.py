"""Ahorro mensual por compensación y retorno simple de la inversión.

Ahorro = ajuste CFE con el FP actual - ajuste CFE con el FP objetivo
(ajuste: positivo = cargo, negativo = bonificación). Así el ahorro incluye la
penalización evitada **y** la bonificación incremental hasta el objetivo, pero
nunca la bonificación que el cliente ya recibe hoy (a diferencia de la
fórmula simplificada de la plantilla).
"""

from __future__ import annotations

import math

from power_factor.config import CfeTariffParams
from power_factor.diagnose import FP_ABS_TOL, cfe_adjustment_mxn


def monthly_savings_mxn(
    fp_actual: float, subtotal: float, fp_objetivo: float, params: CfeTariffParams
) -> float:
    """Ahorro mensual estimado (>= 0) si el FP pasa de `fp_actual` a `fp_objetivo`.

    SUPUESTO conservador: se usa `fp_objetivo` aunque el banco comercial
    (redondeado hacia arriba) deje el FP algo por encima.
    """
    if fp_actual > fp_objetivo or math.isclose(fp_actual, fp_objetivo, abs_tol=FP_ABS_TOL):
        return 0.0
    actual = cfe_adjustment_mxn(fp_actual, subtotal, params)
    objetivo = cfe_adjustment_mxn(fp_objetivo, subtotal, params)
    return max(actual - objetivo, 0.0)


def simple_roi_months(costo_banco_mxn: float | None, ahorro_mensual_mxn: float) -> float | None:
    """Meses para recuperar la inversión. `None` si no hay ahorro o no hay costo válido."""
    if costo_banco_mxn is None or costo_banco_mxn <= 0 or ahorro_mensual_mxn <= 0:
        return None
    return costo_banco_mxn / ahorro_mensual_mxn


def template_savings_mxn(fp_actual: float, subtotal: float, umbral: float = 0.90) -> float:
    """Fórmula simplificada de la plantilla COIL: |FP - 0.90| / 0.90 · subtotal.

    Se calcula solo para comparar. Cuenta como "ahorro" la bonificación que
    el cliente ya recibe (p. ej. FP 0.93) y usa una escala lineal que no es la
    de CFE.
    """
    return abs(fp_actual - umbral) / umbral * subtotal
