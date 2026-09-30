import pytest

from power_factor.config import PRESETS, CfeTariffParams, Settings


def test_defaults_are_documented_assumptions() -> None:
    s = Settings()
    assert s.fp_objetivo == 0.95
    assert s.voltaje_v == 13_200
    assert s.frecuencia_hz == 60
    assert s.conexion == "estrella"
    assert s.negative_kw_policy == "reject"
    assert s.tamanos_comerciales_kvar[0] == 5 and s.tamanos_comerciales_kvar[-1] == 100


def test_preset_480_delta() -> None:
    s = PRESETS["480_delta"]
    assert (s.voltaje_v, s.conexion) == (480, "delta")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fp_objetivo": 0.85},
        {"fp_objetivo": 1.01},
        {"voltaje_v": 0},
        {"frecuencia_hz": -60},
        {"conexion": "zigzag"},
        {"negative_kw_policy": "ignore"},
        {"tamanos_comerciales_kvar": ()},
        {"tamanos_comerciales_kvar": (10, 5)},
        {"tamanos_comerciales_kvar": (0, 5)},
        {"tolerancia_consistencia_fp": -0.1},
    ],
)
def test_invalid_settings_fail_fast(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Settings(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("kwargs", [{"umbral_fp": 1.0}, {"factor_penalizacion": 0}])
def test_invalid_tariff_params(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        CfeTariffParams(**kwargs)
