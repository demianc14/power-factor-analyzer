from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from power_factor.schemas import OPTIONAL_INPUT_COLUMNS, REQUIRED_INPUT_COLUMNS

SAMPLE_XLSX = Path(__file__).resolve().parents[1] / "data" / "sample" / "coil_sample.xlsx"


def base_row(**overrides: Any) -> dict[str, Any]:
    """Fila válida de la Hoja 1 (valores ficticios, como texto donde el xlsx trae texto)."""
    row: dict[str, Any] = {
        "id_registro": "TEST_202601",
        "cliente": "Cliente Test",
        "mes": 1,
        "anio": 2026,
        "consumo_total_kwh": 40_000,
        "demanda_max_kw": 71,
        "consumo_reactivo_kvarh": 18_900,
        "fp_actual": "0.9048",
        "subtotal": 100_000,
        "costo_banco_capturado_mxn": 85_000,
        "fuente_datos": "ficticio",
        "observaciones": "",
        "texto_recibo_original": "",
        "captura_manual_validada": "SI",
        "pdf_nombre": "",
    }
    row.update(overrides)
    return row


@pytest.fixture
def make_df() -> Callable[..., pd.DataFrame]:
    def _make(*rows: dict[str, Any]) -> pd.DataFrame:
        cols = list(REQUIRED_INPUT_COLUMNS) + list(OPTIONAL_INPUT_COLUMNS)
        return pd.DataFrame(list(rows), columns=cols).astype(object)

    return _make


@pytest.fixture
def sample_xlsx() -> Path:
    return SAMPLE_XLSX
