import math

import pytest

from power_factor.compensation import (
    capacitance_per_phase_uf,
    required_kvar,
    suggest_commercial_size,
)
from power_factor.config import SERIE_COMERCIAL_KVAR


def test_qc_hand_check_p71_fp09048_to_095() -> None:
    # tan(acos 0.9048) = 0.47065 ; tan(acos 0.95) = 0.32868 ; 71 · 0.14197 = 10.08
    assert required_kvar(71, 0.9048, 0.95) == pytest.approx(10.079, abs=1e-3)


def test_qc_zero_when_target_already_met() -> None:
    assert required_kvar(71, 0.95, 0.95) == 0.0
    assert required_kvar(71, 0.97, 0.95) == 0.0


def test_qc_template_rows() -> None:
    assert required_kvar(420, 0.84, 0.95) == pytest.approx(133.25, abs=0.01)
    assert required_kvar(415, 0.90, 0.95) == pytest.approx(64.59, abs=0.01)


@pytest.mark.parametrize(
    ("p", "fp1", "fp2"), [(0, 0.9, 0.95), (-71, 0.9, 0.95), (71, 0, 0.95), (71, 0.9, 1.2)]
)
def test_qc_invalid_inputs(p: float, fp1: float, fp2: float) -> None:
    with pytest.raises(ValueError):
        required_kvar(p, fp1, fp2)


def test_capacitance_star_13200() -> None:
    # C = Qc·1000 / (ω·V²) = 10079 / (376.99 · 13200²) = 0.1534 µF
    qc = required_kvar(71, 0.9048, 0.95)
    assert capacitance_per_phase_uf(qc, 13_200, 60, "estrella") == pytest.approx(0.1534, abs=1e-4)


def test_capacitance_delta_480() -> None:
    qc = required_kvar(71, 0.9048, 0.95)
    assert capacitance_per_phase_uf(qc, 480, 60, "delta") == pytest.approx(38.68, abs=0.01)


def test_delta_is_one_third_of_star_at_same_voltage() -> None:
    estrella = capacitance_per_phase_uf(50, 480, 60, "estrella")
    delta = capacitance_per_phase_uf(50, 480, 60, "delta")
    assert delta == pytest.approx(estrella / 3)


def test_capacitance_physics_from_scratch() -> None:
    # Estrella: Q por fase = Qc/3 con V_fase = V/√3 -> C = (Qc/3) / (ω·(V/√3)²).
    qc, v, f = 25.0, 440.0, 60.0
    omega = 2 * math.pi * f
    c_fase = (qc * 1000 / 3) / (omega * (v / math.sqrt(3)) ** 2) * 1e6
    assert capacitance_per_phase_uf(qc, v, f, "estrella") == pytest.approx(c_fase)


@pytest.mark.parametrize(
    ("qc", "v", "f", "con"),
    [(-1, 480, 60, "delta"), (10, 0, 60, "delta"), (10, 480, 0, "delta"), (10, 480, 60, "zz")],
)
def test_capacitance_invalid(qc: float, v: float, f: float, con: str) -> None:
    with pytest.raises(ValueError):
        capacitance_per_phase_uf(qc, v, f, con)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("qc", "total", "unidades", "excede"),
    [
        (0.0, 0.0, (), False),
        (10.079, 15.0, (15.0,), False),
        (10.0, 10.0, (10.0,), False),
        (10.0 + 1e-12, 10.0, (10.0,), False),
        (64.59, 75.0, (75.0,), False),
        (100.0, 100.0, (100.0,), False),
        (102.4, 105.0, (100.0, 5.0), True),
        (133.25, 140.0, (100.0, 40.0), True),
        (200.0, 200.0, (100.0, 100.0), True),
    ],
)
def test_suggest_commercial_size(
    qc: float, total: float, unidades: tuple[float, ...], excede: bool
) -> None:
    s = suggest_commercial_size(qc, SERIE_COMERCIAL_KVAR)
    assert (s.total_kvar, s.unidades, s.excede_serie) == (total, unidades, excede)


def test_bank_description() -> None:
    assert suggest_commercial_size(0, SERIE_COMERCIAL_KVAR).describe() == "sin banco"
    assert suggest_commercial_size(12, SERIE_COMERCIAL_KVAR).describe() == "15 kVAr"
    assert suggest_commercial_size(133, SERIE_COMERCIAL_KVAR).describe() == "140 kVAr (100 + 40)"


def test_suggest_invalid() -> None:
    with pytest.raises(ValueError):
        suggest_commercial_size(-1, SERIE_COMERCIAL_KVAR)
    with pytest.raises(ValueError):
        suggest_commercial_size(10, ())
