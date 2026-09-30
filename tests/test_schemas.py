from typing import Any

import pytest
from pydantic import ValidationError

from power_factor.schemas import BillingRecord


def _record(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id_registro": "X_202601",
        "cliente": "X",
        "mes": 1,
        "anio": 2026,
        "consumo_total_kwh": 1000.0,
        "demanda_max_kw": 71.0,
        "consumo_reactivo_kvarh": 400.0,
        "fp_actual": 0.9,
        "subtotal": 1000.0,
        "costo_banco_capturado_mxn": 5000.0,
        "fila_excel": 2,
    }
    data.update(overrides)
    return data


def test_valid_record_and_derived_period() -> None:
    r = BillingRecord(**_record(mes=3))
    assert r.periodo == "2026-03"
    assert r.indice_mes == 2026 * 12 + 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"fp_actual": 0.0},
        {"fp_actual": 1.2},
        {"demanda_max_kw": 0.0},
        {"demanda_max_kw": -71.0},
        {"subtotal": -1.0},
        {"mes": 13},
        {"id_registro": ""},
        {"costo_banco_capturado_mxn": 0.0},
        {"columna_extra": 1},
    ],
)
def test_physical_ranges_fail_fast(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        BillingRecord(**_record(**overrides))


def test_record_is_immutable() -> None:
    r = BillingRecord(**_record())
    with pytest.raises(ValidationError):
        r.fp_actual = 0.5  # type: ignore[misc]
