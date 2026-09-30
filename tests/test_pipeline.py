"""End-to-end sobre los xlsx de ejemplo (datos ficticios) de data/sample/."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from power_factor.config import Settings
from power_factor.pipeline import run_pipeline
from power_factor.report import SHEET2, SHEET3, SHEET_COMPARACION
from power_factor.schemas import SHEET2_COLUMNS, SHEET3_COLUMNS

FECHA = date(2026, 9, 30)
STRESS_XLSX = Path(__file__).resolve().parents[1] / "data" / "sample" / "stress_cases.xlsx"


def test_end_to_end_sample(sample_xlsx: Path, tmp_path: Path) -> None:
    result = run_pipeline(sample_xlsx, tmp_path / "analisis.xlsx", fecha=FECHA)

    assert result.report.filas_originales == 5
    assert result.report.filas_validas == 5
    # La plantilla trae fp_actual incongruente con kWh/kVArh en 2 filas: aviso, no bloqueo.
    assert result.report.conteo_por_tipo() == {"fp_inconsistente_con_consumos": 2}

    libro = pd.read_excel(result.output_xlsx, sheet_name=None)
    assert list(libro)[:3] == ["01_Datos_Facturacion", SHEET2, SHEET3]
    s2, s3 = libro[SHEET2].set_index("id_registro"), libro[SHEET3].set_index("id_registro")
    assert ("id_registro", *s2.columns) == SHEET2_COLUMNS
    assert ("id_registro", *s3.columns) == SHEET3_COLUMNS

    assert s2.loc["ARNESES_202601", "estado_fp"] == "Penalización"
    assert s2.loc["ARNESES_202601", "q_requerida_kvar"] == pytest.approx(133.25)
    assert s2.loc["ARNESES_202601", "tamano_comercial_sugerido_kvar"] == 140
    assert s2.loc["ARNESES_202603", "estado_fp"] == "Neutro"
    assert s2.loc["ARNESES_202603", "impacto_neto_mxn"] == 0
    assert s2.loc["ARNESES_202603", "ahorro_mensual_estimado_mxn"] == pytest.approx(2580.26)
    assert s2.loc["METALBAJIO_202602", "estado_fp"] == "Bonificación"
    assert s2.loc["METALBAJIO_202602", "impacto_neto_mxn"] == pytest.approx(1233.06)
    assert (s2["fp_objetivo"] == 0.95).all()

    comp = libro[SHEET_COMPARACION].set_index("id_registro")
    # La plantilla cuenta como ahorro la bonificación ya recibida; nosotros no.
    assert comp.loc["METALBAJIO_202602", "ahorro_plantilla"] == pytest.approx(5096.67)
    assert comp.loc["METALBAJIO_202602", "ahorro_mensual_estimado_mxn"] < 1000

    assert s3["resumen_reporte"].str.len().min() > 40
    assert result.plot_png is not None and result.plot_png.exists()
    assert result.quality_csv.exists()


def test_end_to_end_stress_cases(tmp_path: Path) -> None:
    result = run_pipeline(STRESS_XLSX, tmp_path / "stress.xlsx", fecha=FECHA, plot=False)
    assert result.report.filas_originales == 11
    assert result.report.filas_validas == 4
    assert result.report.conteo_por_tipo() == {
        "duplicado_exacto": 1,
        "fp_irrecuperable": 3,
        "fp_no_numerico": 1,
        "fp_porcentaje_reescalado": 1,
        "kw_negativo_rechazado": 1,
        "subtotal_invalido": 1,
    }
    assert result.plot_png is None
    s2 = result.sheets[SHEET2].set_index("id_registro")
    # Todas las filas con id siguen visibles en la hoja 02 (el duplicado exacto, una vez).
    assert len(s2) == 10
    assert s2.loc["STRESS_202603", "estado_fp"] == "Sin diagnóstico"
    assert s2.loc["STRESS_202602", "q_requerida_kvar"] == pytest.approx(10.08)


def test_negative_kw_abs_policy_end_to_end(tmp_path: Path) -> None:
    result = run_pipeline(STRESS_XLSX, tmp_path / "s.xlsx", Settings(negative_kw_policy="abs"),
                          fecha=FECHA, plot=False)
    assert result.report.filas_validas == 5
    assert "kw_negativo_abs" in result.report.conteo_por_tipo()


def test_no_valid_rows_skips_plot(tmp_path: Path) -> None:
    df = pd.read_excel(STRESS_XLSX, sheet_name="Hoja 1", dtype=object)
    df["fp_actual"] = "1.2"
    path = tmp_path / "in.xlsx"
    df.to_excel(path, sheet_name="Hoja 1", index=False)
    result = run_pipeline(path, tmp_path / "out.xlsx", fecha=FECHA)
    assert result.analyses == () and result.plot_png is None
