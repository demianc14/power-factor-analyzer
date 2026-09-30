from pathlib import Path

import pandas as pd
import pytest

from power_factor.extract import read_billing_sheet, require_columns
from tests.conftest import base_row


def _write(path: Path, df: pd.DataFrame, sheet: str = "Hoja 1") -> Path:
    df.to_excel(path, sheet_name=sheet, index=False)
    return path


def test_missing_columns_error_names_every_missing_column() -> None:
    df = pd.DataFrame([base_row()]).drop(columns=["fp_actual", "subtotal"])
    with pytest.raises(ValueError, match=r"\['fp_actual', 'subtotal'\]"):
        require_columns(df)


def test_read_keeps_raw_values_and_strips_headers(tmp_path: Path) -> None:
    df = pd.DataFrame([base_row(fp_actual="0.84")])
    df = df.rename(columns={"fp_actual": " fp_actual "})
    out = read_billing_sheet(_write(tmp_path / "in.xlsx", df))
    assert "fp_actual" in out.columns
    assert out.loc[0, "fp_actual"] == "0.84"  # sigue siendo texto: clean decide


def test_read_accepts_contract_sheet_name(tmp_path: Path) -> None:
    path = _write(tmp_path / "in.xlsx", pd.DataFrame([base_row()]), sheet="01_Datos_Facturacion")
    assert len(read_billing_sheet(path)) == 1


def test_read_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_billing_sheet(tmp_path / "nope.xlsx")


def test_read_unknown_sheet(tmp_path: Path) -> None:
    path = _write(tmp_path / "in.xlsx", pd.DataFrame([base_row()]), sheet="Otra")
    with pytest.raises(ValueError, match="No se encontró la hoja"):
        read_billing_sheet(path)
    with pytest.raises(ValueError, match="no existe"):
        read_billing_sheet(path, sheet="Hoja 9")


def test_read_explicit_sheet(tmp_path: Path) -> None:
    path = _write(tmp_path / "in.xlsx", pd.DataFrame([base_row()]), sheet="Otra")
    assert len(read_billing_sheet(path, sheet="Otra")) == 1


def test_read_fails_fast_on_missing_column(tmp_path: Path) -> None:
    df = pd.DataFrame([base_row()]).drop(columns=["demanda_max_kw"])
    with pytest.raises(ValueError, match="demanda_max_kw"):
        read_billing_sheet(_write(tmp_path / "in.xlsx", df))
