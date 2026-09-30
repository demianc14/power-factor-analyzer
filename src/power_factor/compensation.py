"""Compensación reactiva: Qc, capacitancia por fase y banco comercial sugerido.

    Qc = P · (tan φ1 - tan φ2),  φ = acos(FP)

Capacitancia por fase con V = voltaje de línea y ω = 2πf:
    estrella: cada fase ve V/√3 y aporta Qc/3  ->  C = Qc / (ω · V²)
    delta:    cada fase ve V    y aporta Qc/3  ->  C = Qc / (3 · ω · V²)
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from power_factor.config import Conexion
from power_factor.diagnose import FP_ABS_TOL

# Holgura para que un Qc de 10.0000000001 kVAr no salte al siguiente tamaño comercial.
KVAR_ABS_TOL = 1e-9


@dataclass(frozen=True)
class BankSuggestion:
    """Banco sugerido. `unidades` lista los tamaños comerciales que lo componen."""

    total_kvar: float
    unidades: tuple[float, ...]
    excede_serie: bool

    def describe(self) -> str:
        if not self.unidades:
            return "sin banco"
        if len(self.unidades) == 1:
            return f"{self.total_kvar:g} kVAr"
        return f"{self.total_kvar:g} kVAr ({' + '.join(f'{u:g}' for u in self.unidades)})"


def required_kvar(p_kw: float, fp_actual: float, fp_objetivo: float) -> float:
    """kVAr necesarios para llevar el FP de `fp_actual` a `fp_objetivo`. 0 si ya se cumple."""
    if p_kw <= 0:
        raise ValueError(f"P debe ser positiva: {p_kw}")
    for nombre, fp in (("fp_actual", fp_actual), ("fp_objetivo", fp_objetivo)):
        if not 0 < fp <= 1:
            raise ValueError(f"{nombre} fuera de (0, 1]: {fp}")
    if fp_actual > fp_objetivo or math.isclose(fp_actual, fp_objetivo, abs_tol=FP_ABS_TOL):
        return 0.0
    return p_kw * (math.tan(math.acos(fp_actual)) - math.tan(math.acos(fp_objetivo)))


def capacitance_per_phase_uf(
    qc_kvar: float, voltaje_v: float, frecuencia_hz: float, conexion: Conexion
) -> float:
    """Capacitancia por fase en µF para un banco trifásico de `qc_kvar`."""
    if qc_kvar < 0:
        raise ValueError(f"Qc no puede ser negativa: {qc_kvar}")
    if voltaje_v <= 0 or frecuencia_hz <= 0:
        raise ValueError("voltaje y frecuencia deben ser positivos")
    omega = 2 * math.pi * frecuencia_hz
    q_var = qc_kvar * 1000
    if conexion == "estrella":
        c_f = q_var / (omega * voltaje_v**2)
    elif conexion == "delta":
        c_f = q_var / (3 * omega * voltaje_v**2)
    else:
        raise ValueError(f"conexión desconocida: {conexion!r}")
    return c_f * 1e6


def suggest_commercial_size(qc_kvar: float, tamanos: Sequence[float]) -> BankSuggestion:
    """Siguiente tamaño comercial >= Qc.

    Si Qc supera el tamaño máximo de la serie: n unidades del máximo + el
    siguiente tamaño que cubra el remanente (regla greedy, simple y
    explicable; no garantiza la combinación de menor kVAr total) y se marca
    `excede_serie` para revisión de ingeniería.
    """
    if qc_kvar < 0:
        raise ValueError(f"Qc no puede ser negativa: {qc_kvar}")
    if not tamanos:
        raise ValueError("la serie comercial está vacía")
    serie = sorted(tamanos)
    if qc_kvar <= KVAR_ABS_TOL:
        return BankSuggestion(0.0, (), excede_serie=False)

    maximo = serie[-1]
    unidades: list[float] = []
    restante = qc_kvar
    while restante > maximo + KVAR_ABS_TOL:
        unidades.append(maximo)
        restante -= maximo
    if restante > KVAR_ABS_TOL:
        unidades.append(next(t for t in serie if t >= restante - KVAR_ABS_TOL))
    return BankSuggestion(
        total_kvar=float(sum(unidades)),
        unidades=tuple(sorted(unidades, reverse=True)),
        excede_serie=qc_kvar > maximo + KVAR_ABS_TOL,
    )
