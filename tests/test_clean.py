from collections.abc import Callable
from typing import Any

import pandas as pd
import pytest

from power_factor.clean import (
    IssueType,
    clean_billing,
    parse_number,
    parse_power_factor,
)
from power_factor.config import Settings
from tests.conftest import base_row

MakeDf = Callable[..., pd.DataFrame]


def _types(result: Any) -> list[str]:
    return [i.tipo.value for i in result.report.issues]


# ----------------------------------------------------------------- parse_number


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("37,303", 37303.0),
        ("$121,407.09", 121407.09),
        (" 71 ", 71.0),
        (71, 71.0),
        (-627.56, -627.56),
        ("", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_parse_number(raw: Any, expected: float | None) -> None:
    assert parse_number(raw) == expected


@pytest.mark.parametrize("raw", ["0,84", "abc", True, "inf"])
def test_parse_number_rejects_ambiguous_or_non_numeric(raw: Any) -> None:
    with pytest.raises(ValueError):
        parse_number(raw)


# ----------------------------------------------------------------- parse_power_factor


def test_fp_text_is_converted_to_float() -> None:
    r = parse_power_factor("0.84")
    assert r.value == pytest.approx(0.84) and r.issue is None


def test_fp_exact_boundary_090_is_valid() -> None:
    r = parse_power_factor("0.90")
    assert r.value == 0.9 and r.issue is None


def test_fp_one_is_valid() -> None:
    assert parse_power_factor(1).value == 1.0


def test_fp_percent_is_rescaled_with_warning() -> None:
    r = parse_power_factor("90.48")
    assert r.value == pytest.approx(0.9048)
    assert r.issue is IssueType.FP_PORCENTAJE_REESCALADO


@pytest.mark.parametrize("raw", [50, 100])
def test_fp_percent_range_is_inclusive(raw: float) -> None:
    assert parse_power_factor(raw).issue is IssueType.FP_PORCENTAJE_REESCALADO


def test_fp_with_explicit_percent_sign() -> None:
    assert parse_power_factor("90.48%").value == pytest.approx(0.9048)
    assert parse_power_factor("120%").issue is IssueType.FP_IRRECUPERABLE


def test_fp_12_is_unrecoverable_not_0012() -> None:
    """Bug del cuaderno original: 1.2 se 'corregía' a 0.012."""
    r = parse_power_factor("1.2")
    assert r.value is None
    assert r.issue is IssueType.FP_IRRECUPERABLE


@pytest.mark.parametrize("raw", ["0", 0, "-0.5", "49.99", "100.5", "150"])
def test_fp_out_of_range_is_unrecoverable(raw: Any) -> None:
    r = parse_power_factor(raw)
    assert r.value is None and r.issue is IssueType.FP_IRRECUPERABLE


def test_fp_missing_and_non_numeric() -> None:
    assert parse_power_factor(None).issue is IssueType.FP_FALTANTE
    assert parse_power_factor("n/d").issue is IssueType.FP_NO_NUMERICO


# ----------------------------------------------------------------- clean_billing


def test_valid_row_passes_clean(make_df: MakeDf) -> None:
    result = clean_billing(make_df(base_row()), Settings())
    assert len(result.records) == 1
    assert result.records[0].fp_actual == pytest.approx(0.9048)
    assert result.report.issues == ()


def test_unrecoverable_fp_row_is_excluded_and_reported(make_df: MakeDf) -> None:
    df = make_df(base_row(), base_row(id_registro="BAD_202602", mes=2, fp_actual="1.2"))
    result = clean_billing(df, Settings())
    assert [r.id_registro for r in result.records] == ["TEST_202601"]
    assert result.report.filas_originales == 2
    assert result.report.filas_excluidas == 1
    issue = result.report.issues[0]
    assert (issue.fila_excel, issue.valor_original, issue.severidad) == (3, "1.2", "excluida")
    assert result.report.motivos_exclusion()["BAD_202602"]


def test_negative_kw_rejected_by_default(make_df: MakeDf) -> None:
    result = clean_billing(make_df(base_row(demanda_max_kw=-71)), Settings())
    assert result.records == ()
    assert _types(result) == ["kw_negativo_rechazado"]


def test_negative_kw_abs_policy_keeps_row_with_warning(make_df: MakeDf) -> None:
    result = clean_billing(make_df(base_row(demanda_max_kw=-71)),
                           Settings(negative_kw_policy="abs"))
    assert result.records[0].demanda_max_kw == 71
    assert _types(result) == ["kw_negativo_abs"]


@pytest.mark.parametrize("kw", [0, None, "n/d"])
def test_zero_or_missing_kw_is_excluded(make_df: MakeDf, kw: Any) -> None:
    result = clean_billing(make_df(base_row(demanda_max_kw=kw)), Settings())
    assert result.records == () and _types(result) == ["kw_invalido"]


@pytest.mark.parametrize("subtotal", [None, -5, "abc"])
def test_invalid_subtotal_is_excluded(make_df: MakeDf, subtotal: Any) -> None:
    result = clean_billing(make_df(base_row(subtotal=subtotal)), Settings())
    assert result.records == () and _types(result) == ["subtotal_invalido"]


def test_missing_id_client_and_period(make_df: MakeDf) -> None:
    result = clean_billing(make_df(base_row(id_registro=None, cliente="", mes=13)), Settings())
    assert result.records == ()
    assert _types(result) == ["id_faltante", "cliente_faltante", "periodo_invalido"]


def test_missing_bank_cost_is_a_warning(make_df: MakeDf) -> None:
    result = clean_billing(make_df(base_row(costo_banco_capturado_mxn=None)), Settings())
    assert result.records[0].costo_banco_capturado_mxn is None
    assert _types(result) == ["costo_banco_invalido"]


def test_inconsistent_fp_vs_consumption_is_a_warning(make_df: MakeDf) -> None:
    # 128500 kWh / 68400 kVArh implican FP 0.883, no 0.84.
    df = make_df(base_row(consumo_total_kwh=128_500, consumo_reactivo_kvarh=68_400,
                          fp_actual="0.84"))
    result = clean_billing(df, Settings())
    assert len(result.records) == 1
    assert _types(result) == ["fp_inconsistente_con_consumos"]


def test_invalid_consumption_skips_consistency_check(make_df: MakeDf) -> None:
    result = clean_billing(make_df(base_row(consumo_reactivo_kvarh="abc")), Settings())
    assert result.records[0].consumo_reactivo_kvarh is None
    assert _types(result) == ["consumo_invalido"]


def test_exact_duplicate_keeps_first(make_df: MakeDf) -> None:
    result = clean_billing(make_df(base_row(), base_row()), Settings())
    assert len(result.records) == 1
    assert _types(result) == ["duplicado_exacto"]


def test_conflicting_duplicate_id_excludes_all(make_df: MakeDf) -> None:
    df = make_df(base_row(), base_row(fp_actual="0.95"))
    result = clean_billing(df, Settings())
    assert result.records == ()
    assert _types(result) == ["id_duplicado_conflictivo"] * 2


def test_same_client_period_with_different_ids_excludes_both(make_df: MakeDf) -> None:
    df = make_df(base_row(), base_row(id_registro="OTRO_202601"))
    result = clean_billing(df, Settings())
    assert result.records == ()
    assert result.report.conteo_por_tipo() == {"periodo_duplicado": 2}


def test_report_frames(make_df: MakeDf) -> None:
    df = make_df(base_row(), base_row(id_registro="B_202602", mes=2, fp_actual="90.48"))
    report = clean_billing(df, Settings()).report
    assert list(report.to_frame()["tipo"]) == ["fp_porcentaje_reescalado"]
    resumen = dict(zip(report.summary_frame()["metrica"], report.summary_frame()["valor"],
                       strict=True))
    assert resumen["filas_originales"] == 2
    assert resumen["filas_validas"] == 2
    assert resumen["anomalia:fp_porcentaje_reescalado"] == 1


@pytest.mark.parametrize(("mes", "anio"), [("enero", 2026), (1.5, 2026), (1, None)])
def test_non_integer_period_is_excluded(make_df: MakeDf, mes: Any, anio: Any) -> None:
    result = clean_billing(make_df(base_row(mes=mes, anio=anio)), Settings())
    assert result.records == () and _types(result) == ["periodo_invalido"]


def test_non_numeric_bank_cost_is_a_warning(make_df: MakeDf) -> None:
    result = clean_billing(make_df(base_row(costo_banco_capturado_mxn="por definir")), Settings())
    assert result.records[0].costo_banco_capturado_mxn is None
