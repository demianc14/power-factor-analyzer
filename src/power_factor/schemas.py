"""Contratos de datos (Pydantic): columnas de entrada y filas de salida.

Los nombres de columnas y su orden vienen del contrato de integración del
proyecto COIL (hojas 01/02/03). Los modelos son `frozen` y `extra="forbid"`
para que cualquier desviación truene en la frontera y no en medio de un cálculo.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# Hoja 1: columnas sin las cuales no se puede diagnosticar ni calcular.
REQUIRED_INPUT_COLUMNS: tuple[str, ...] = (
    "id_registro",
    "cliente",
    "mes",
    "anio",
    "consumo_total_kwh",
    "demanda_max_kw",
    "consumo_reactivo_kvarh",
    "fp_actual",
    "subtotal",
    "costo_banco_capturado_mxn",
)
# Hoja 1: columnas de trazabilidad; si faltan, el pipeline sigue.
OPTIONAL_INPUT_COLUMNS: tuple[str, ...] = (
    "fuente_datos",
    "observaciones",
    "texto_recibo_original",
    "captura_manual_validada",
    "pdf_nombre",
)

SHEET2_COLUMNS: tuple[str, ...] = (
    "id_registro",
    "estado_fp",
    "comentario_diagnostico",
    "penalizacion_mxn",
    "bonificacion_mxn",
    "impacto_neto_mxn",
    "fp_objetivo",
    "q_requerida_kvar",
    "capacitancia_uf",
    "tamano_comercial_sugerido_kvar",
    "ahorro_mensual_estimado_mxn",
    "roi_meses",
)

SHEET3_COLUMNS: tuple[str, ...] = (
    "id_registro",
    "cliente",
    "fp_actual",
    "estado_fp",
    "impacto_neto_mxn",
    "tamano_comercial_sugerido_kvar",
    "roi_meses",
    "resumen_reporte",
    "fecha_ultima_actualizacion",
)

NonEmptyStr = Annotated[str, Field(min_length=1)]
NonNegative = Annotated[float, Field(ge=0)]
Positive = Annotated[float, Field(gt=0)]
Money = float


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BillingRecord(_Frozen):
    """Una fila de la Hoja 1 ya limpia: un cliente en un mes."""

    id_registro: NonEmptyStr
    cliente: NonEmptyStr
    mes: Annotated[int, Field(ge=1, le=12)]
    anio: Annotated[int, Field(ge=2000, le=2100)]
    consumo_total_kwh: NonNegative | None
    demanda_max_kw: Positive
    consumo_reactivo_kvarh: NonNegative | None
    fp_actual: Annotated[float, Field(gt=0, le=1)]
    subtotal: NonNegative
    costo_banco_capturado_mxn: Positive | None
    fila_excel: Annotated[int, Field(ge=2)]

    @property
    def periodo(self) -> str:
        return f"{self.anio:04d}-{self.mes:02d}"

    @property
    def indice_mes(self) -> int:
        """Número de mes absoluto: permite detectar huecos entre periodos."""
        return self.anio * 12 + (self.mes - 1)


class Sheet2Row(_Frozen):
    """Fila de 02_Analisis_Economico_Tecnico (mismo orden que el contrato)."""

    id_registro: NonEmptyStr
    estado_fp: NonEmptyStr
    comentario_diagnostico: NonEmptyStr
    penalizacion_mxn: NonNegative | None
    bonificacion_mxn: NonNegative | None
    impacto_neto_mxn: Money | None
    fp_objetivo: Annotated[float, Field(gt=0, le=1)]
    q_requerida_kvar: NonNegative | None
    capacitancia_uf: NonNegative | None
    tamano_comercial_sugerido_kvar: NonNegative | None
    ahorro_mensual_estimado_mxn: NonNegative | None
    roi_meses: Positive | None


class Sheet3Row(_Frozen):
    """Fila de 03_Resultados_Negocio (mismo orden que el contrato)."""

    id_registro: NonEmptyStr
    cliente: str
    fp_actual: Annotated[float, Field(gt=0, le=1)] | None
    estado_fp: NonEmptyStr
    impacto_neto_mxn: Money | None
    tamano_comercial_sugerido_kvar: NonNegative | None
    roi_meses: Positive | None
    resumen_reporte: NonEmptyStr
    fecha_ultima_actualizacion: date


assert tuple(Sheet2Row.model_fields) == SHEET2_COLUMNS
assert tuple(Sheet3Row.model_fields) == SHEET3_COLUMNS
