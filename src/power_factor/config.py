"""Parámetros del pipeline.

Todo lo que no viene en el recibo (voltaje, frecuencia, conexión del banco) o que
depende de una regla de negocio (FP objetivo, fórmula CFE, serie comercial,
política ante kW negativo) vive aquí como parámetro explícito, nunca como un
número mágico dentro de un cálculo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Conexion = Literal["estrella", "delta"]
NegativeKwPolicy = Literal["reject", "abs"]

CONEXIONES: tuple[Conexion, ...] = ("estrella", "delta")
NEGATIVE_KW_POLICIES: tuple[NegativeKwPolicy, ...] = ("reject", "abs")

# SUPUESTO: serie comercial "didáctica" definida en el documento de arquitectura del COIL.
SERIE_COMERCIAL_KVAR: tuple[float, ...] = (5, 10, 15, 20, 25, 30, 40, 50, 60, 75, 100)


@dataclass(frozen=True)
class CfeTariffParams:
    """Fórmula de cargo/bonificación por factor de potencia.

    TODO verificar contra tarifa vigente: coeficientes y topes tomados de la
    fórmula estándar publicada por CFE para tarifas de media tensión. Contra el
    recibo de referencia reproduce la bonificación con error de 0.31 MXN solo
    si se usa el FP del histórico (92.22 %), no el del bloque principal (90.48 %).
    """

    umbral_fp: float = 0.90
    factor_penalizacion: float = 3 / 5
    tope_penalizacion_pct: float = 120.0
    factor_bonificacion: float = 1 / 4
    tope_bonificacion_pct: float = 2.5

    def __post_init__(self) -> None:
        if not 0 < self.umbral_fp < 1:
            raise ValueError(f"umbral_fp debe estar en (0, 1); se recibió {self.umbral_fp}")
        for nombre in (
            "factor_penalizacion",
            "tope_penalizacion_pct",
            "factor_bonificacion",
            "tope_bonificacion_pct",
        ):
            if getattr(self, nombre) <= 0:
                raise ValueError(f"{nombre} debe ser positivo")


@dataclass(frozen=True)
class Settings:
    """Configuración completa de una corrida del pipeline."""

    fp_objetivo: float = 0.95
    # SUPUESTO: el xlsx no trae voltaje ni conexión. 13.2 kV es típico de GDMTH (media tensión).
    voltaje_v: float = 13_200.0
    frecuencia_hz: float = 60.0
    conexion: Conexion = "estrella"
    tamanos_comerciales_kvar: tuple[float, ...] = SERIE_COMERCIAL_KVAR
    negative_kw_policy: NegativeKwPolicy = "reject"
    # Diferencia máxima tolerada entre fp_actual y el FP calculado con kWh/kVArh.
    tolerancia_consistencia_fp: float = 0.02
    cfe: CfeTariffParams = field(default_factory=CfeTariffParams)

    def __post_init__(self) -> None:
        if not self.cfe.umbral_fp <= self.fp_objetivo <= 1:
            raise ValueError(
                f"fp_objetivo debe estar en [{self.cfe.umbral_fp}, 1]; "
                f"se recibió {self.fp_objetivo}"
            )
        if self.voltaje_v <= 0:
            raise ValueError(f"voltaje_v debe ser positivo; se recibió {self.voltaje_v}")
        if self.frecuencia_hz <= 0:
            raise ValueError(f"frecuencia_hz debe ser positiva; se recibió {self.frecuencia_hz}")
        if self.conexion not in CONEXIONES:
            raise ValueError(f"conexion debe ser una de {CONEXIONES}; se recibió {self.conexion!r}")
        if self.negative_kw_policy not in NEGATIVE_KW_POLICIES:
            raise ValueError(
                f"negative_kw_policy debe ser una de {NEGATIVE_KW_POLICIES}; "
                f"se recibió {self.negative_kw_policy!r}"
            )
        tamanos = self.tamanos_comerciales_kvar
        if not tamanos or any(t <= 0 for t in tamanos) or list(tamanos) != sorted(set(tamanos)):
            raise ValueError(
                "tamanos_comerciales_kvar debe ser una secuencia no vacía, positiva, "
                "estrictamente creciente"
            )
        if self.tolerancia_consistencia_fp < 0:
            raise ValueError("tolerancia_consistencia_fp no puede ser negativa")


PRESETS: dict[str, Settings] = {
    # Caso base: acometida de media tensión.
    "13200_estrella": Settings(),
    # Escenario de baja tensión del cuaderno de Semana 3.
    "480_delta": Settings(voltaje_v=480.0, conexion="delta"),
    # Supuesto oficial del documento del proyecto COIL (440 VAC trifásico).
    "440_delta": Settings(voltaje_v=440.0, conexion="delta"),
}
