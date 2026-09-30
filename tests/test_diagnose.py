import pytest

from power_factor.config import CfeTariffParams
from power_factor.diagnose import (
    EstadoFP,
    cfe_adjustment_mxn,
    cfe_adjustment_pct,
    classify_fp,
    diagnostic_comment,
    economic_impact,
)

P = CfeTariffParams()


@pytest.mark.parametrize(
    ("fp", "estado"),
    [
        (0.84, EstadoFP.PENALIZACION),
        (0.8999, EstadoFP.PENALIZACION),
        (0.90, EstadoFP.NEUTRO),
        (float("0.90"), EstadoFP.NEUTRO),
        (0.9001, EstadoFP.BONIFICACION),
        (0.93, EstadoFP.BONIFICACION),
        (0.95, EstadoFP.META_CUMPLIDA),
        (0.99, EstadoFP.META_CUMPLIDA),
    ],
)
def test_classify_fp(fp: float, estado: EstadoFP) -> None:
    assert classify_fp(fp, fp_objetivo=0.95) is estado


def test_classify_fp_boundary_is_float_safe() -> None:
    # 0.3 * 3 = 0.8999999999999999 en binario: debe seguir siendo "Neutro".
    assert classify_fp(0.3 * 3, fp_objetivo=0.95) is EstadoFP.NEUTRO


@pytest.mark.parametrize("fp", [0.0, -0.1, 1.2])
def test_classify_rejects_invalid_fp(fp: float) -> None:
    with pytest.raises(ValueError):
        classify_fp(fp, 0.95)


def test_adjustment_zero_at_090() -> None:
    assert cfe_adjustment_pct(0.90, P) == 0.0


def test_penalty_formula() -> None:
    # 3/5 · (0.9/0.84 - 1) · 100 = 4.2857 %
    assert cfe_adjustment_pct(0.84, P) == pytest.approx(4.285714, rel=1e-6)


def test_penalty_is_capped_at_120() -> None:
    assert cfe_adjustment_pct(0.2, P) == 120.0


def test_bonus_formula_and_cap() -> None:
    # 1/4 · (1 - 0.9/0.95) · 100 = 1.3158 %
    assert cfe_adjustment_pct(0.95, P) == pytest.approx(-1.315789, rel=1e-6)
    assert cfe_adjustment_pct(1.0, P) == pytest.approx(-2.5)


def test_reference_receipt_is_reproduced_with_historic_fp() -> None:
    """Recibo real DIC 25: bonificación -627.56 MXN sobre Energía = 104,225.03.

    Con el FP del bloque principal (0.9048) la fórmula da -138.23: NO cuadra.
    Con el FP del histórico (0.9222) da -627.25 (diferencia 0.31 MXN).
    Pregunta abierta: qué FP usa CFE para facturar.
    """
    base = 104_225.03
    assert cfe_adjustment_mxn(0.9048, base, P) == pytest.approx(-138.23, abs=0.01)
    assert cfe_adjustment_mxn(0.9222, base, P) == pytest.approx(-627.56, abs=0.5)


def test_adjustment_rejects_negative_base() -> None:
    with pytest.raises(ValueError):
        cfe_adjustment_mxn(0.9, -1, P)


def test_economic_impact_signs() -> None:
    pen = economic_impact(0.84, 198_500, P)
    assert pen.penalizacion_mxn == pytest.approx(8507.14, abs=0.01)
    assert pen.bonificacion_mxn == 0.0
    assert pen.impacto_neto_mxn == pytest.approx(-8507.14, abs=0.01)

    bon = economic_impact(0.93, 152_900, P)
    assert bon.penalizacion_mxn == 0.0
    assert bon.impacto_neto_mxn == pytest.approx(1233.06, abs=0.01)

    neutro = economic_impact(0.90, 196_100, P)
    assert neutro.impacto_neto_mxn == 0.0


@pytest.mark.parametrize(
    ("estado", "fragmento"),
    [
        (EstadoFP.PENALIZACION, "cargo"),
        (EstadoFP.NEUTRO, "sin cargo"),
        (EstadoFP.BONIFICACION, "bonificación"),
        (EstadoFP.META_CUMPLIDA, "no requiere"),
    ],
)
def test_diagnostic_comment(estado: EstadoFP, fragmento: str) -> None:
    assert fragmento in diagnostic_comment(estado, 0.9, 0.95, 1.0)
