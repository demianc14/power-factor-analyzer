import pytest

from power_factor.config import CfeTariffParams
from power_factor.roi import monthly_savings_mxn, simple_roi_months, template_savings_mxn

P = CfeTariffParams()


def test_savings_penalty_avoided_plus_incremental_bonus() -> None:
    # FP 0.84 -> 0.95 sobre 198,500: cargo 4.2857 % + bonif. 1.3158 % = 5.6015 %
    assert monthly_savings_mxn(0.84, 198_500, 0.95, P) == pytest.approx(11118.98, abs=0.01)


def test_savings_at_090_is_the_bonus_reachable_at_target() -> None:
    # ARNESES_202603: FP 0.90 no paga cargo, pero compensar a 0.95 daría 1.3158 % de bonificación.
    assert monthly_savings_mxn(0.90, 196_100, 0.95, P) == pytest.approx(2580.26, abs=0.01)


def test_savings_do_not_count_the_bonus_already_received() -> None:
    # METALBAJIO_202602: FP 0.93 ya recibe 0.8065 %; solo cuenta el incremento hasta 1.3158 %.
    ahorro = monthly_savings_mxn(0.93, 152_900, 0.95, P)
    assert ahorro == pytest.approx(152_900 * (1.315789 - 0.806452) / 100, abs=0.01)
    assert ahorro < template_savings_mxn(0.93, 152_900)


@pytest.mark.parametrize("fp", [0.95, 0.97, 1.0])
def test_no_savings_when_target_met(fp: float) -> None:
    assert monthly_savings_mxn(fp, 150_000, 0.95, P) == 0.0


def test_roi_months() -> None:
    assert simple_roi_months(92_000, 11_118.98) == pytest.approx(8.274, abs=1e-3)


@pytest.mark.parametrize(("costo", "ahorro"), [(92_000, 0.0), (92_000, -5.0), (None, 100.0),
                                               (0, 100.0)])
def test_roi_is_none_instead_of_dividing_by_zero(costo: float | None, ahorro: float) -> None:
    assert simple_roi_months(costo, ahorro) is None


def test_roi_none_when_fp_already_meets_target() -> None:
    ahorro = monthly_savings_mxn(0.96, 150_000, 0.95, P)
    assert simple_roi_months(70_000, ahorro) is None


def test_template_formula_matches_prefilled_template_values() -> None:
    """Valores prellenados en la Hoja 2 de la plantilla COIL."""
    assert template_savings_mxn(0.84, 198_500) == pytest.approx(13233.33, abs=0.01)
    assert template_savings_mxn(0.87, 201_300) == pytest.approx(6710.00, abs=0.01)
    assert template_savings_mxn(0.90, 196_100) == 0.0
    assert template_savings_mxn(0.88, 148_700) == pytest.approx(3304.44, abs=0.01)
    assert template_savings_mxn(0.93, 152_900) == pytest.approx(5096.67, abs=0.01)
