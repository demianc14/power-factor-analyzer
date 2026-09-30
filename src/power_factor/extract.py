"""Extract: lee la hoja de entrada tal cual, sin lógica de negocio.

Todo se lee como `object` para que `clean` vea el valor original (p. ej. el
texto '0.84' o '90.48%') y pueda reportarlo si no es válido.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from power_factor.schemas import REQUIRED_INPUT_COLUMNS

DEFAULT_INPUT_SHEET = "Hoja 1"
# Nombre oficial del contrato COIL; se acepta como alternativa.
CONTRACT_INPUT_SHEET = "01_Datos_Facturacion"


def require_columns(df: pd.DataFrame, required: Iterable[str] = REQUIRED_INPUT_COLUMNS) -> None:
    """Falla rápido si falta cualquier columna obligatoria, nombrándolas todas."""
    faltantes = [c for c in required if c not in df.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas obligatorias en la hoja de entrada: {faltantes}")


def _resolve_sheet(path: Path, sheet: str | None) -> str:
    disponibles = pd.ExcelFile(path).sheet_names
    if sheet is not None:
        if sheet not in disponibles:
            raise ValueError(f"La hoja {sheet!r} no existe en {path.name}; hay: {disponibles}")
        return sheet
    for candidata in (DEFAULT_INPUT_SHEET, CONTRACT_INPUT_SHEET):
        if candidata in disponibles:
            return candidata
    raise ValueError(
        f"No se encontró la hoja de entrada ({DEFAULT_INPUT_SHEET!r} o "
        f"{CONTRACT_INPUT_SHEET!r}) en {path.name}; hay: {disponibles}"
    )


def read_billing_sheet(path: str | Path, sheet: str | None = None) -> pd.DataFrame:
    """Lee la hoja de facturación y valida el contrato de columnas.

    Solo se normalizan los encabezados (espacios alrededor), porque copiar el
    contrato a Google Sheets suele introducirlos y el nombre de columna es
    estructura, no dato.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo de entrada: {path}")
    nombre_hoja = _resolve_sheet(path, sheet)
    df = pd.read_excel(path, sheet_name=nombre_hoja, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    require_columns(df)
    return df
