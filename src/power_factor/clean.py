"""Transform (1/2): normalización y detección de anomalías.

Principio: lo que se puede corregir sin ambigüedad se corrige y se reporta
como aviso; lo que requeriría adivinar se excluye y se reporta. Nunca se
imputa un valor. Todo queda en un `DataQualityReport` cuantificado.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

import pandas as pd

from power_factor.config import Settings
from power_factor.schemas import BillingRecord

Severidad = Literal["excluida", "aviso"]

# Primera fila de datos en Excel (la 1 es el encabezado).
EXCEL_FIRST_DATA_ROW = 2
# Un FP entre estos límites se interpreta como porcentaje mal escalado (90.48 -> 0.9048).
PERCENT_MIN = 50.0
PERCENT_MAX = 100.0

_THOUSANDS_RE = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")


class IssueType(StrEnum):
    ID_FALTANTE = "id_faltante"
    CLIENTE_FALTANTE = "cliente_faltante"
    PERIODO_INVALIDO = "periodo_invalido"
    FP_FALTANTE = "fp_faltante"
    FP_NO_NUMERICO = "fp_no_numerico"
    FP_IRRECUPERABLE = "fp_irrecuperable"
    FP_PORCENTAJE_REESCALADO = "fp_porcentaje_reescalado"
    FP_INCONSISTENTE_CON_CONSUMOS = "fp_inconsistente_con_consumos"
    KW_INVALIDO = "kw_invalido"
    KW_NEGATIVO_RECHAZADO = "kw_negativo_rechazado"
    KW_NEGATIVO_ABS = "kw_negativo_abs"
    SUBTOTAL_INVALIDO = "subtotal_invalido"
    CONSUMO_INVALIDO = "consumo_invalido"
    COSTO_BANCO_INVALIDO = "costo_banco_invalido"
    DUPLICADO_EXACTO = "duplicado_exacto"
    ID_DUPLICADO_CONFLICTIVO = "id_duplicado_conflictivo"
    PERIODO_DUPLICADO = "periodo_duplicado"


@dataclass(frozen=True)
class DataQualityIssue:
    fila_excel: int
    id_registro: str | None
    columna: str
    tipo: IssueType
    severidad: Severidad
    valor_original: str
    detalle: str


@dataclass(frozen=True)
class DataQualityReport:
    filas_originales: int
    filas_validas: int
    issues: tuple[DataQualityIssue, ...]

    @property
    def filas_excluidas(self) -> int:
        return self.filas_originales - self.filas_validas

    def conteo_por_tipo(self) -> dict[str, int]:
        conteo: dict[str, int] = defaultdict(int)
        for issue in self.issues:
            conteo[issue.tipo.value] += 1
        return dict(sorted(conteo.items()))

    def motivos_exclusion(self) -> dict[str, list[str]]:
        """id_registro -> detalles de las anomalías que excluyeron la fila."""
        motivos: dict[str, list[str]] = defaultdict(list)
        for issue in self.issues:
            if issue.severidad == "excluida" and issue.id_registro:
                motivos[issue.id_registro].append(issue.detalle)
        return dict(motivos)

    def to_frame(self) -> pd.DataFrame:
        columnas = [
            "fila_excel",
            "id_registro",
            "columna",
            "tipo",
            "severidad",
            "valor_original",
            "detalle",
        ]
        filas = [
            [i.fila_excel, i.id_registro, i.columna, i.tipo.value, i.severidad,
             i.valor_original, i.detalle]
            for i in self.issues
        ]
        return pd.DataFrame(filas, columns=columnas)

    def summary_frame(self) -> pd.DataFrame:
        filas: list[tuple[str, int]] = [
            ("filas_originales", self.filas_originales),
            ("filas_validas", self.filas_validas),
            ("filas_excluidas", self.filas_excluidas),
        ]
        filas += [(f"anomalia:{tipo}", n) for tipo, n in self.conteo_por_tipo().items()]
        return pd.DataFrame(filas, columns=["metrica", "valor"])


@dataclass(frozen=True)
class CleanResult:
    records: tuple[BillingRecord, ...]
    report: DataQualityReport


@dataclass(frozen=True)
class FpParse:
    value: float | None
    issue: IssueType | None
    detalle: str


# --------------------------------------------------------------------------- parsers


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value.strip() == ""


def parse_number(value: Any) -> float | None:
    """Convierte '37,303', '$121,407.09' o 71 a float. `None` si falta.

    Lanza `ValueError` si el texto no es numérico o si la coma es ambigua
    ('0,84' puede ser decimal o miles: no se adivina).
    """
    if is_missing(value):
        return None
    if isinstance(value, bool):
        raise ValueError(f"valor booleano no numérico: {value!r}")
    if isinstance(value, int | float):
        numero = float(value)
    else:
        texto = str(value).strip().replace("$", "").replace(" ", "")
        if "," in texto:
            if not _THOUSANDS_RE.match(texto):
                raise ValueError(f"separador de coma ambiguo en {value!r}")
            texto = texto.replace(",", "")
        try:
            numero = float(texto)
        except ValueError:
            raise ValueError(f"texto no numérico: {value!r}") from None
    if not math.isfinite(numero):
        raise ValueError(f"valor no finito: {value!r}")
    return numero


def parse_power_factor(raw: Any) -> FpParse:
    """Aplica la regla de conversión de FP.

    - (0, 1]     -> válido tal cual.
    - [50, 100]  -> porcentaje mal escalado: se divide entre 100 (aviso).
    - '90.48%'   -> el signo % es explícito: se divide entre 100 y se valida.
    - (1, 50), > 100 o <= 0 -> irrecuperable (p. ej. 1.2 NO se convierte en 0.012).
    """
    if is_missing(raw):
        return FpParse(None, IssueType.FP_FALTANTE, "fp_actual vacío")
    texto = str(raw).strip()
    es_porcentaje_explicito = texto.endswith("%")
    try:
        numero = parse_number(texto.rstrip("%") if es_porcentaje_explicito else raw)
    except ValueError as exc:
        return FpParse(None, IssueType.FP_NO_NUMERICO, f"fp_actual no numérico ({exc})")
    assert numero is not None  # is_missing ya descartó vacíos

    if es_porcentaje_explicito:
        numero /= 100
        if 0 < numero <= 1:
            return FpParse(numero, None, "")
        return FpParse(None, IssueType.FP_IRRECUPERABLE, f"FP {texto} fuera de (0, 100] %")
    if 0 < numero <= 1:
        return FpParse(numero, None, "")
    if PERCENT_MIN <= numero <= PERCENT_MAX:
        return FpParse(
            numero / 100,
            IssueType.FP_PORCENTAJE_REESCALADO,
            f"FP {numero:g} interpretado como porcentaje -> {numero / 100:g}",
        )
    return FpParse(
        None,
        IssueType.FP_IRRECUPERABLE,
        f"FP {numero:g} fuera de (0, 1] y fuera de [{PERCENT_MIN:g}, {PERCENT_MAX:g}]: "
        "no se imputa",
    )


def _parse_int(value: Any) -> int | None:
    numero = parse_number(value)
    if numero is None or not numero.is_integer():
        return None
    return int(numero)


# --------------------------------------------------------------------------- limpieza


class _RowIssues:
    """Acumula las anomalías de una fila."""

    def __init__(self, fila_excel: int, id_registro: str | None, raw: pd.Series) -> None:
        self.fila_excel = fila_excel
        self.id_registro = id_registro
        self.raw = raw
        self.items: list[DataQualityIssue] = []

    def add(self, columna: str, tipo: IssueType, severidad: Severidad, detalle: str) -> None:
        valor = self.raw.get(columna) if columna in self.raw.index else None
        self.items.append(
            DataQualityIssue(
                fila_excel=self.fila_excel,
                id_registro=self.id_registro,
                columna=columna,
                tipo=tipo,
                severidad=severidad,
                valor_original="" if is_missing(valor) else str(valor),
                detalle=detalle,
            )
        )

    @property
    def excluida(self) -> bool:
        return any(i.severidad == "excluida" for i in self.items)


def _text(value: Any) -> str | None:
    return None if is_missing(value) else str(value).strip()


def _clean_row(fila: _RowIssues, settings: Settings) -> dict[str, Any] | None:
    """Valida y normaliza una fila; `None` si queda excluida."""
    raw = fila.raw
    if fila.id_registro is None:
        fila.add("id_registro", IssueType.ID_FALTANTE, "excluida", "id_registro vacío")
    cliente = _text(raw["cliente"])
    if cliente is None:
        fila.add("cliente", IssueType.CLIENTE_FALTANTE, "excluida", "cliente vacío")

    try:
        mes, anio = _parse_int(raw["mes"]), _parse_int(raw["anio"])
    except ValueError:
        mes = anio = None
    if mes is None or anio is None or not 1 <= mes <= 12 or not 2000 <= anio <= 2100:
        fila.add("mes", IssueType.PERIODO_INVALIDO, "excluida", "mes/anio inválido")

    fp = parse_power_factor(raw["fp_actual"])
    if fp.issue is not None:
        severidad: Severidad = "aviso" if fp.value is not None else "excluida"
        fila.add("fp_actual", fp.issue, severidad, fp.detalle)

    demanda = _clean_demand(fila, settings)

    try:
        subtotal = parse_number(raw["subtotal"])
    except ValueError:
        subtotal = None
    if subtotal is None or subtotal < 0:
        fila.add("subtotal", IssueType.SUBTOTAL_INVALIDO, "excluida",
                 "subtotal vacío, no numérico o negativo: sin base para el ajuste CFE")

    consumos: dict[str, float | None] = {}
    for col in ("consumo_total_kwh", "consumo_reactivo_kvarh"):
        try:
            valor = parse_number(raw[col])
            invalido = valor is not None and valor < 0
        except ValueError:
            valor, invalido = None, True
        if invalido:
            fila.add(col, IssueType.CONSUMO_INVALIDO, "aviso",
                     f"{col} no numérico o negativo: se omite la verificación de consistencia")
            valor = None
        consumos[col] = valor

    try:
        costo = parse_number(raw["costo_banco_capturado_mxn"])
    except ValueError:
        costo = None
    if costo is None or costo <= 0:
        fila.add("costo_banco_capturado_mxn", IssueType.COSTO_BANCO_INVALIDO, "aviso",
                 "costo del banco vacío o no positivo: no se puede calcular ROI")
        costo = None

    if fila.excluida:
        return None

    assert fp.value is not None and demanda is not None and subtotal is not None
    _check_consistency(fila, fp.value, consumos, settings.tolerancia_consistencia_fp)
    return {
        "id_registro": fila.id_registro,
        "cliente": cliente,
        "mes": mes,
        "anio": anio,
        "consumo_total_kwh": consumos["consumo_total_kwh"],
        "demanda_max_kw": demanda,
        "consumo_reactivo_kvarh": consumos["consumo_reactivo_kvarh"],
        "fp_actual": fp.value,
        "subtotal": subtotal,
        "costo_banco_capturado_mxn": costo,
        "fila_excel": fila.fila_excel,
    }


def _clean_demand(fila: _RowIssues, settings: Settings) -> float | None:
    try:
        kw = parse_number(fila.raw["demanda_max_kw"])
    except ValueError:
        kw = None
    if kw is None or kw == 0:
        fila.add("demanda_max_kw", IssueType.KW_INVALIDO, "excluida",
                 "demanda_max_kw vacía, no numérica o cero")
        return None
    if kw > 0:
        return kw
    if settings.negative_kw_policy == "abs":
        fila.add("demanda_max_kw", IssueType.KW_NEGATIVO_ABS, "aviso",
                 f"kW negativo ({kw:g}) convertido a {abs(kw):g} por política 'abs'")
        return abs(kw)
    fila.add("demanda_max_kw", IssueType.KW_NEGATIVO_RECHAZADO, "excluida",
             f"kW negativo ({kw:g}): posible flujo inverso o convención de signo; "
             "requiere revisión (política 'reject')")
    return None


def _check_consistency(
    fila: _RowIssues, fp: float, consumos: dict[str, float | None], tolerancia: float
) -> None:
    kwh, kvarh = consumos["consumo_total_kwh"], consumos["consumo_reactivo_kvarh"]
    if kwh is None or kvarh is None or kwh <= 0:
        return
    fp_calculado = kwh / math.hypot(kwh, kvarh)
    if abs(fp_calculado - fp) > tolerancia:
        fila.add("fp_actual", IssueType.FP_INCONSISTENTE_CON_CONSUMOS, "aviso",
                 f"fp_actual={fp:.4f} pero kWh/kVArh implican {fp_calculado:.4f} "
                 f"(tolerancia {tolerancia}); se usa fp_actual")


def _row_signature(raw: pd.Series) -> tuple[str, ...]:
    return tuple("" if is_missing(v) else str(v).strip() for v in raw.tolist())


def clean_billing(df: pd.DataFrame, settings: Settings) -> CleanResult:
    """Limpia la Hoja 1 y devuelve registros válidos + reporte de calidad."""
    filas = [
        _RowIssues(EXCEL_FIRST_DATA_ROW + pos, _text(raw["id_registro"]), raw)
        for pos, (_, raw) in enumerate(df.iterrows())
    ]

    # 1) id_registro duplicado: copia exacta -> se conserva la primera; si difieren -> ambiguo.
    por_id: dict[str, list[_RowIssues]] = defaultdict(list)
    for fila in filas:
        if fila.id_registro is not None:
            por_id[fila.id_registro].append(fila)
    for id_registro, grupo in por_id.items():
        if len(grupo) < 2:
            continue
        if len({_row_signature(f.raw) for f in grupo}) == 1:
            for copia in grupo[1:]:
                copia.add("id_registro", IssueType.DUPLICADO_EXACTO, "excluida",
                          f"copia exacta de la fila {grupo[0].fila_excel}; se conserva esa")
        else:
            filas_grupo = [f.fila_excel for f in grupo]
            for f in grupo:
                f.add("id_registro", IssueType.ID_DUPLICADO_CONFLICTIVO, "excluida",
                      f"{id_registro} aparece con valores distintos en filas {filas_grupo}")

    # 2) Validación por fila.
    candidatos: list[tuple[_RowIssues, dict[str, Any]]] = []
    for fila in filas:
        if fila.excluida:
            continue
        datos = _clean_row(fila, settings)
        if datos is not None:
            candidatos.append((fila, datos))

    # 3) Mismo cliente y periodo con distinto id: no se sabe cuál recibo es el bueno.
    por_periodo: dict[tuple[str, int, int], list[_RowIssues]] = defaultdict(list)
    for fila, datos in candidatos:
        por_periodo[(datos["cliente"].casefold(), datos["anio"], datos["mes"])].append(fila)
    for (_, anio, mes), grupo in por_periodo.items():
        if len(grupo) > 1:
            ids = [f.id_registro for f in grupo]
            for f in grupo:
                f.add("mes", IssueType.PERIODO_DUPLICADO, "excluida",
                      f"periodo {anio}-{mes:02d} repetido para el mismo cliente en {ids}")

    records = tuple(BillingRecord(**datos) for fila, datos in candidatos if not fila.excluida)
    issues = tuple(i for fila in filas for i in fila.items)
    report = DataQualityReport(filas_originales=len(df), filas_validas=len(records), issues=issues)
    return CleanResult(records=records, report=report)
