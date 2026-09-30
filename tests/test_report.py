from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from power_factor.analysis import ExcludedRecord, analyze_record
from power_factor.config import Settings
from power_factor.diagnose import EstadoFP
from power_factor.report import (
    SIN_DIAGNOSTICO,
    build_assumptions_sheet,
    build_comparison_sheet,
    build_resumen,
    build_sheet2,
    build_sheet3,
    write_workbook,
)
from power_factor.schemas import SHEET2_COLUMNS, SHEET3_COLUMNS, BillingRecord

FECHA = date(2026, 9, 30)


def _rec(**overrides: Any) -> BillingRecord:
    data: dict[str, Any] = {
        "id_registro": "X_202601", "cliente": "Cliente X", "mes": 1, "anio": 2026,
        "consumo_total_kwh": None, "demanda_max_kw": 71.0, "consumo_reactivo_kvarh": None,
        "fp_actual": 0.9048, "subtotal": 100_000.0, "costo_banco_capturado_mxn": 85_000.0,
        "fila_excel": 2,
    }
    data.update(overrides)
    return BillingRecord(**data)


def test_analyze_record_hand_checked_values() -> None:
    a = analyze_record(_rec(), Settings())
    assert a.estado is EstadoFP.BONIFICACION
    assert a.q_requerida_kvar == pytest.approx(10.079, abs=1e-3)
    assert a.capacitancia_uf == pytest.approx(0.1534, abs=1e-4)
    assert a.banco.total_kvar == 15
    assert a.roi_meses is not None and a.roi_meses > 0


def test_analyze_record_480_delta_scenario() -> None:
    a = analyze_record(_rec(), Settings(voltaje_v=480, conexion="delta"))
    assert a.capacitancia_uf == pytest.approx(38.68, abs=0.01)
    # El Qc no depende del voltaje ni de la conexión, solo la capacitancia.
    assert a.q_requerida_kvar == pytest.approx(10.079, abs=1e-3)


def test_meta_cumplida_has_no_bank_and_no_roi() -> None:
    a = analyze_record(_rec(fp_actual=0.97), Settings())
    assert a.estado is EstadoFP.META_CUMPLIDA
    assert (a.q_requerida_kvar, a.banco.total_kvar, a.ahorro_mensual_mxn) == (0, 0, 0)
    assert a.roi_meses is None
    assert "No requiere compensación" in build_resumen(a)


def test_bank_exceeding_series_is_flagged_everywhere() -> None:
    a = analyze_record(_rec(demanda_max_kw=420, fp_actual=0.84), Settings())
    assert a.banco.excede_serie
    assert "excede la serie" in a.comentario
    assert "validar con ingeniería" in build_resumen(a)


def test_resumen_mentions_state_impact_bank_and_roi() -> None:
    a = analyze_record(_rec(fp_actual=0.84), Settings())
    texto = build_resumen(a)
    for fragmento in ("Penalización", "cargo estimado", "kVAr", "meses"):
        assert fragmento in texto


def test_resumen_neutral_state() -> None:
    texto = build_resumen(analyze_record(_rec(fp_actual=0.90), Settings()))
    assert "sin cargo ni bonificación" in texto


def test_resumen_without_bank_cost() -> None:
    a = analyze_record(_rec(fp_actual=0.84, costo_banco_capturado_mxn=None), Settings())
    assert a.roi_meses is None
    assert "falta el costo del banco" in build_resumen(a)


def test_resumen_without_savings() -> None:
    # Caso artificial: subtotal 0 -> no hay ahorro aunque haga falta banco.
    a = analyze_record(_rec(fp_actual=0.84, subtotal=0.0), Settings())
    assert "no hay ahorro estimable" in build_resumen(a)


def test_sheet2_and_sheet3_follow_contract_and_include_excluded_rows() -> None:
    ok = analyze_record(_rec(fila_excel=3), Settings())
    excl = ExcludedRecord("BAD_202601", "Cliente X", 2, ("FP 1.2 irrecuperable",))
    s2 = build_sheet2([ok], [excl], Settings())
    s3 = build_sheet3([ok], [excl], FECHA)
    assert tuple(s2.columns) == SHEET2_COLUMNS
    assert tuple(s3.columns) == SHEET3_COLUMNS
    # Orden de la hoja de entrada (fila_excel), no "válidos primero".
    assert list(s2["id_registro"]) == ["BAD_202601", "X_202601"]
    assert s2.loc[0, "estado_fp"] == SIN_DIAGNOSTICO
    assert pd.isna(s2.loc[0, "roi_meses"])
    assert "FP 1.2" in s3.loc[0, "resumen_reporte"]
    assert s3.loc[1, "fecha_ultima_actualizacion"] == FECHA


def test_sheet3_excluded_without_client() -> None:
    s3 = build_sheet3([], [ExcludedRecord("B", None, 2, ("x",))], FECHA)
    assert s3.loc[0, "cliente"] == "dato no disponible"


def test_rounding_rules() -> None:
    s2 = build_sheet2([analyze_record(_rec(fp_actual=0.84123), Settings())], [], Settings())
    s3 = build_sheet3([analyze_record(_rec(fp_actual=0.84123), Settings())], [], FECHA)
    assert s3.loc[0, "fp_actual"] == 0.841
    assert s2.loc[0, "penalizacion_mxn"] == round(s2.loc[0, "penalizacion_mxn"], 2)


def test_no_negative_zero_in_neutral_case() -> None:
    s2 = build_sheet2([analyze_record(_rec(fp_actual=0.90), Settings())], [], Settings())
    for col in ("penalizacion_mxn", "bonificacion_mxn", "impacto_neto_mxn"):
        assert str(s2.loc[0, col]) == "0.0"


def test_comparison_sheet_notes_by_state() -> None:
    analyses = [analyze_record(_rec(id_registro=f"X_2026{i:02d}", mes=i, fp_actual=fp), Settings())
                for i, fp in enumerate([0.84, 0.90, 0.93], start=1)]
    comp = build_comparison_sheet(analyses)
    assert list(comp.columns[:6]) == ["id_registro", "fp_actual", "estado_fp",
                                      "ahorro_mensual_estimado_mxn", "ahorro_plantilla",
                                      "diferencia_vs_plantilla"]
    assert comp.loc[1, "ahorro_plantilla"] == 0.0
    assert pd.isna(comp.loc[1, "roi_plantilla_meses"])
    assert "ya se recibe" in comp.loc[2, "nota"]
    diferencia = comp.loc[0, "ahorro_mensual_estimado_mxn"] - comp.loc[0, "ahorro_plantilla"]
    assert comp.loc[0, "diferencia_vs_plantilla"] == pytest.approx(diferencia, abs=0.01)


def test_assumptions_sheet_lists_every_parameter() -> None:
    df = build_assumptions_sheet(replace(Settings(), voltaje_v=480))
    params = dict(zip(df["parametro"], df["valor"], strict=True))
    assert params["voltaje_v"] == "480"
    assert "cfe.tope_bonificacion_pct" in params
    assert params["base_ajuste_cfe"] == "subtotal"


def test_write_workbook(tmp_path: Path) -> None:
    path = write_workbook(tmp_path / "sub" / "out.xlsx",
                          {"A": pd.DataFrame({"x": [1, 2]}), "B": pd.DataFrame({"y": ["z"]})})
    assert pd.ExcelFile(path).sheet_names == ["A", "B"]
